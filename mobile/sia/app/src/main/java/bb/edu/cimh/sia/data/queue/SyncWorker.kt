package bb.edu.cimh.sia.data.queue

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import bb.edu.cimh.sia.SiaApplication
import java.util.concurrent.TimeUnit

/** Sends queued scans once the network is back (APD §5 "Offline"). */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val container = (applicationContext as SiaApplication).container
        return when (container.scans.drain()) {
            DrainResult.EMPTY -> Result.success()
            DrainResult.RETRY_LATER -> Result.retry()
            // No session: the scans wait; the next login of the same account sends them.
            DrainResult.NO_SESSION -> Result.success()
        }
    }

    companion object {
        private const val NAME = "scan-sync"

        /** APPEND_OR_REPLACE: a scan queued while a run is ending still gets a run of its own. */
        fun schedule(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(NAME, ExistingWorkPolicy.APPEND_OR_REPLACE, request)
        }
    }
}
