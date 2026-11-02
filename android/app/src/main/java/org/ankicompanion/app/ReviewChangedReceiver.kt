package org.ankicompanion.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.SystemClock
import java.util.concurrent.atomic.AtomicLong

/** Wake-up only: no broadcast data is trusted, no UI opens, and reads require provider permission. */
class ReviewChangedReceiver:BroadcastReceiver() {
    companion object {private val last=AtomicLong(0)}
    override fun onReceive(context:Context,intent:Intent) {
        if(intent.action!="org.ankicompanion.app.REVIEWS_CHANGED")return
        val now=SystemClock.elapsedRealtime();val previous=last.get()
        if(now-previous<1000 || !last.compareAndSet(previous,now))return
        // BroadcastReceiver goAsync has a short OS deadline; Anki collection
        // sync may legitimately take longer. Durable JobScheduler work survives
        // process death and this executor gives foreground study immediate wakeup.
        Sync.schedule(context.applicationContext,true)
        Sync.executor.execute {Sync.run(context.applicationContext)}
    }
}
