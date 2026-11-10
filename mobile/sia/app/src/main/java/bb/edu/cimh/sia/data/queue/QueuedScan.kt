package bb.edu.cimh.sia.data.queue

import android.content.Context
import androidx.room.AutoMigration
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/** ORDER_PICK = a unit for one line of a request (M-07), sent to order-svc. ASSIGN/UNASSIGN = issue to a person / return. */
enum class ScanOp { STOW, PICK, RELOCATE, ORDER_PICK, ASSIGN, UNASSIGN }

enum class ScanStatus { PENDING, FAILED }

/**
 * One scan waiting for the server (APD §5 "Offline"). [key] is the `Idempotency-Key`: made once at enqueue and
 * kept across automatic retries, so a scan that reached the server before the connection dropped is not done
 * twice. A row is deleted once the server accepted it; a refused one stays FAILED for M-11.
 */
@Entity(tableName = "scans", indices = [Index("key", unique = true), Index("status")])
data class QueuedScan(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val key: String,
    val op: ScanOp,
    val unit: String,
    /** Stow: the shelf. Relocate: the target shelf. */
    val shelf: String? = null,
    val reason: String? = null,
    val orderId: String? = null,
    /** ORDER_PICK: the request line the unit is for (added in schema 2). */
    val lineId: String? = null,
    /** ASSIGN: the account the unit is issued to (added in schema 3). */
    val assignee: String? = null,
    /** Who scanned: scans of another account are never sent with this one's token. */
    val accountId: String,
    val createdAt: Long,
    val status: ScanStatus = ScanStatus.PENDING,
    val attempts: Int = 0,
    val errorCode: String? = null,
    val errorMessage: String? = null,
)

@Dao
interface ScanDao {
    @Insert
    suspend fun insert(scan: QueuedScan): Long

    @Query("SELECT * FROM scans WHERE id = :id")
    suspend fun get(id: Long): QueuedScan?

    @Query("SELECT * FROM scans WHERE status = 'PENDING' AND accountId = :accountId ORDER BY id LIMIT 1")
    suspend fun nextPending(accountId: String): QueuedScan?

    @Query("UPDATE scans SET attempts = attempts + 1 WHERE id = :id")
    suspend fun countAttempt(id: Long)

    @Query("UPDATE scans SET status = 'FAILED', errorCode = :code, errorMessage = :message WHERE id = :id")
    suspend fun fail(id: Long, code: String?, message: String)

    /** M-11 retry: a new key, because the server keeps (and replays) the refusal for the old one. */
    @Query("UPDATE scans SET status = 'PENDING', key = :key, errorCode = NULL, errorMessage = NULL WHERE id = :id")
    suspend fun retry(id: Long, key: String)

    @Query("DELETE FROM scans WHERE id = :id")
    suspend fun delete(id: Long)

    @Query("DELETE FROM scans")
    suspend fun clear()

    @Query("SELECT * FROM scans WHERE accountId = :accountId ORDER BY id")
    fun observeAll(accountId: String): Flow<List<QueuedScan>>
}

@Database(
    entities = [QueuedScan::class],
    version = 3,
    exportSchema = true,
    autoMigrations = [AutoMigration(from = 1, to = 2), AutoMigration(from = 2, to = 3)],
)
abstract class ScanDatabase : RoomDatabase() {
    abstract fun scans(): ScanDao

    companion object {
        fun open(context: Context): ScanDatabase =
            Room.databaseBuilder(context, ScanDatabase::class.java, "scans.db").build()
    }
}
