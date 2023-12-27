package com.alibaba.fescar.rm.datasource.undo;
import java.sql.Blob;
import com.alibaba.druid.util.JdbcConstants;
import java.sql.Connection;
import com.alibaba.fescar.common.exception.NotSupportYetException;
import java.sql.PreparedStatement;
import com.alibaba.fescar.common.util.BlobUtils;
import java.sql.ResultSet;
import com.alibaba.fescar.common.util.StringUtils;
import java.sql.SQLException;
import com.alibaba.fescar.core.exception.TransactionException;
import com.alibaba.fescar.rm.datasource.ConnectionContext;
import com.alibaba.fescar.rm.datasource.ConnectionProxy;
import com.alibaba.fescar.rm.datasource.DataSourceProxy;
import com.alibaba.fescar.rm.datasource.sql.struct.TableMeta;
import com.alibaba.fescar.rm.datasource.sql.struct.TableMetaCache;
import java.sql.SQLIntegrityConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import static com.alibaba.fescar.core.exception.TransactionExceptionCode.BranchRollbackFailed_Retriable;

/**
 * The type Undo log manager.
 */
public final class UndoLogManager {
  private enum State {
    Normal(0),
    GlobalFinished(1)
    ;

    private int value;

    State(int value) {
      this.value = value;
    }

    public int getValue() {
      return value;
    }
  }

  private static final Logger LOGGER = LoggerFactory.getLogger(UndoLogManager.class);

  private static String UNDO_LOG_TABLE_NAME = "undo_log";

  private static String INSERT_UNDO_LOG_SQL = "INSERT INTO " + UNDO_LOG_TABLE_NAME + "\n" + "\t(branch_id, xid, rollback_info, log_status, log_created, log_modified)\n" + "VALUES (?, ?, ?, ?, now(), now())";

  private static String DELETE_UNDO_LOG_SQL = "DELETE FROM " + UNDO_LOG_TABLE_NAME + "\n" + "\tWHERE branch_id = ? AND xid = ?";

  private static String SELECT_UNDO_LOG_SQL = "SELECT * FROM " + UNDO_LOG_TABLE_NAME + " WHERE  branch_id = ? AND xid = ? FOR UPDATE";

  private UndoLogManager() {
  }

  /**
     * Flush undo logs.
     *
     * @param cp the cp
     * @throws SQLException the sql exception
     */
  public static void flushUndoLogs(ConnectionProxy cp) throws SQLException {
    assertDbSupport(cp.getDbType());
    ConnectionContext connectionContext = cp.getContext();
    String xid = connectionContext.getXid();
    long branchID = connectionContext.getBranchId();
    BranchUndoLog branchUndoLog = new BranchUndoLog();
    branchUndoLog.setXid(xid);
    branchUndoLog.setBranchId(branchID);
    branchUndoLog.setSqlUndoLogs(connectionContext.getUndoItems());
    String undoLogContent = UndoLogParserFactory.getInstance().encode(branchUndoLog);
    if (LOGGER.isDebugEnabled()) {
      LOGGER.debug("Flushing UNDO LOG: " + undoLogContent);
    }
    insertUndoLogWithNormal(xid, branchID, undoLogContent, cp.getTargetConnection());
  }

  private static void assertDbSupport(String dbType) {
    if (!JdbcConstants.MYSQL.equals(dbType)) {
      throw new NotSupportYetException("DbType[" + dbType + "] is not support yet!");
    }
  }

  /**
     * Undo.
     *
     * @param dataSourceProxy the data source proxy
     * @param xid             the xid
     * @param branchId        the branch id
     * @throws TransactionException the transaction exception
     */
  public static void undo(DataSourceProxy dataSourceProxy, String xid, long branchId) throws TransactionException {
    assertDbSupport(dataSourceProxy.getTargetDataSource().getDbType());
    Connection conn = null;
    ResultSet rs = null;
    PreparedStatement selectPST = null;
    for ( ; ; ) {
      try {
        conn = dataSourceProxy.getPlainConnection();
        conn.setAutoCommit(false);
        selectPST = conn.prepareStatement(SELECT_UNDO_LOG_SQL);
        selectPST.setLong(1, branchId);
        selectPST.setString(2, xid);
        rs = selectPST.executeQuery();
        boolean exists = false;
        while (rs.next()) {
          exists = true;
          int state = rs.getInt("log_status");
          if (!canUndo(state)) {
            LOGGER.info("xid {} branch {}, ignore {} undo_log", xid, branchId, state);
            return;
          }
          Blob b = rs.getBlob("rollback_info");
          String rollbackInfo = StringUtils.blob2string(b);
          BranchUndoLog branchUndoLog = UndoLogParserFactory.getInstance().decode(rollbackInfo);
          for (SQLUndoLog sqlUndoLog : branchUndoLog.getSqlUndoLogs()) {
            TableMeta tableMeta = TableMetaCache.getTableMeta(dataSourceProxy, sqlUndoLog.getTableName());
            sqlUndoLog.setTableMeta(tableMeta);
            AbstractUndoExecutor undoExecutor = UndoExecutorFactory.getUndoExecutor(dataSourceProxy.getDbType(), sqlUndoLog);
            undoExecutor.executeOn(conn);
          }
        }
        if (exists) {
          deleteUndoLog(xid, branchId, conn);
          conn.commit();
          LOGGER.info("xid {} branch {}, undo_log deleted with {}", xid, branchId, State.GlobalFinished.name());
        } else {
          insertUndoLogWithGlobalFinished(xid, branchId, conn);
          conn.commit();
          LOGGER.info("xid {} branch {}, undo_log added with {}", xid, branchId, State.GlobalFinished.name());
        }
        return;
      } catch (SQLIntegrityConstraintViolationException e) {
        LOGGER.info("xid {} branch {}, undo_log inserted, retry rollback", xid, branchId);
      } catch (Throwable e) {
        if (conn != null) {
          try {
            conn.rollback();
          } catch (SQLException rollbackEx) {
            LOGGER.warn("Failed to close JDBC resource while undo ... ", rollbackEx);
          }
        }
        throw new TransactionException(BranchRollbackFailed_Retriable, String.format("%s/%s", branchId, xid), e);
      } finally {
        try {
          if (rs != null) {
            rs.close();
          }
          if (selectPST != null) {
            selectPST.close();
          }
          if (conn != null) {
            conn.close();
          }
        } catch (SQLException closeEx) {
          LOGGER.warn("Failed to close JDBC resource while undo ... ", closeEx);
        }
      }
    }
  }

  /**
     * Delete undo log.
     *
     * @param xid      the xid
     * @param branchId the branch id
     * @param conn     the conn
     * @throws SQLException the sql exception
     */
  public static void deleteUndoLog(String xid, long branchId, Connection conn) throws SQLException {
    PreparedStatement deletePST = conn.prepareStatement(DELETE_UNDO_LOG_SQL);
    deletePST.setLong(1, branchId);
    deletePST.setString(2, xid);
    deletePST.executeUpdate();
  }

  private static void insertUndoLogWithNormal(String xid, long branchID, String undoLogContent, Connection conn) throws SQLException {
    insertUndoLog(xid, branchID, undoLogContent, State.Normal, conn);
  }

  private static void insertUndoLogWithGlobalFinished(String xid, long branchID, Connection conn) throws SQLException {
    insertUndoLog(xid, branchID, "{}", State.GlobalFinished, conn);
  }

  private static void insertUndoLog(String xid, long branchID, String undoLogContent, State state, Connection conn) throws SQLException {
    PreparedStatement pst = null;
    try {
      pst = conn.prepareStatement(INSERT_UNDO_LOG_SQL);
      pst.setLong(1, branchID);
      pst.setString(2, xid);
      pst.setBlob(3, BlobUtils.string2blob(undoLogContent));
      pst.setInt(4, state.getValue());
      pst.executeUpdate();
    } catch (Exception e) {
      if (e instanceof SQLException) {
        throw (SQLException) e;
      } else {
        throw new SQLException(e);
      }
    } finally {
      if (pst != null) {
        pst.close();
      }
    }
  }

  private static boolean canUndo(int state) {
    return state == State.Normal.getValue();
  }
}