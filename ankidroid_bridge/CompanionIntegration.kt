// SPDX-License-Identifier: GPL-3.0-or-later
// AnkiCompanion extension for AnkiDroid 2.25.3. No collection SQL writes.
package com.ichi2.anki

import android.content.Context
import android.content.Intent
import android.database.MatrixCursor
import android.net.Uri
import android.os.Bundle
import anki.sync.SyncCollectionResponse
import anki.collection.opChanges
import com.ichi2.anki.observability.ChangeManager
import com.ichi2.anki.common.preferences.sharedPrefs
import com.ichi2.anki.CollectionManager.withCol
import com.ichi2.anki.settings.Prefs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.concurrent.atomic.AtomicBoolean

object CompanionIntegration {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutex = Mutex()
    private val queued = AtomicBoolean(false)
    private val requested = AtomicBoolean(false)
    @Volatile private var app: Context? = null
    private fun prefs() = app!!.getSharedPreferences("companion_bridge", Context.MODE_PRIVATE)
    fun initialize(context: Context) { app = context.applicationContext }
    private fun enabled() = app != null && prefs().getBoolean("enabled", false)

    fun status(): Bundle = Bundle().apply {
        putInt("api_version", 1)
        putBoolean("history", true)
        putBoolean("native_sync", true)
        putBoolean("enabled", enabled())
        putString("sync_status", if (app == null) "not initialized" else prefs().getString("sync_status", "not yet synced"))
        putLong("synced_ms", if (app == null) 0 else prefs().getLong("synced_ms", 0))
        putLong("generation", if (app == null) 0 else prefs().getLong("generation", 0))
    }

    fun configure(context: Context, options: Bundle): Bundle {
        initialize(context)
        val wasEnabled = enabled()
        // All automatic review hooks are in the supported new reviewer.
        context.sharedPrefs().edit().putBoolean("newReviewer", true).putBoolean("newReviewerOptions", true).apply()
        prefs().edit().putBoolean("enabled", options.getBoolean("enabled", true))
            .putString("parent_deck_id", options.getString("parent_deck_id", ""))
            .putString("clearance", options.getString("clearance", "new_and_reviews")).apply()
        if (!wasEnabled && enabled()) requestSync()
        return status()
    }

    fun changed() {
        val context = app ?: return
        if (!enabled()) return
        // Only a wake-up signal. The companion trusts no broadcast payload;
        // it reads the permission-protected provider and its authenticated server.
        context.sendBroadcast(Intent("org.ankicompanion.app.REVIEWS_CHANGED")
            .setClassName("org.ankicompanion.app", "org.ankicompanion.app.ReviewChangedReceiver"))
    }

    fun requestSync(): Bundle {
        if (!enabled()) return status()
        // A committed answer wakes asynchronous collection synchronization;
        // the reviewer never awaits this IO. Reviews arriving during an
        // existing pass schedule a subsequent pass, not a dropped request.
        requested.set(true)
        if (queued.compareAndSet(false,true)) {
            scope.launch {
                try {
                    do {
                        delay(700) // group closely-spaced answers (<5s target)
                        requested.set(false)
                        synchronize()
                    } while (requested.get())
                } finally {
                    queued.set(false)
                    if (requested.get()) requestSync()
                }
            }
        }
        return status()
    }

    suspend fun synchronize(notifyUi: Boolean = true): Boolean {
        if (!enabled()) return false
        return mutex.withLock {
            val auth = syncAuth()
            if (auth == null) {
                prefs().edit().putString("sync_status", "Sign in and complete initial collection sync in AnkiDroid").apply()
                return@withLock false
            }
            prefs().edit().putString("sync_status", "syncing").apply()
            try {
                val before = withCol { db.queryString("SELECT COUNT(*)||':'||COALESCE(SUM(reps),0)||':'||COALESCE(MAX(mod),0) FROM cards") }
                val result = withCol { syncCollection(auth, syncMedia = false) }
                if (result.hasNewEndpoint() && result.newEndpoint.isNotEmpty()) Prefs.currentSyncUri = result.newEndpoint
                if (result.required != SyncCollectionResponse.ChangesRequired.NO_CHANGES) {
                    prefs().edit().putString("sync_status", "Initial/full sync needs a direction choice in AnkiDroid").apply()
                    return@withLock false
                }
                withCol { _loadScheduler(); notetypes.clearCache() }
                prefs().edit().putString("sync_status", "synced")
                    .putLong("synced_ms", System.currentTimeMillis())
                    .putLong("generation", prefs().getLong("generation", 0) + 1).apply()
                changed()
                val after = withCol { db.queryString("SELECT COUNT(*)||':'||COALESCE(SUM(reps),0)||':'||COALESCE(MAX(mod),0) FROM cards") }
                if (notifyUi && before != after) ChangeManager.publish(opChanges { studyQueues = true })
                true
            } catch (e: Exception) {
                // Avoid credentials/remote response bodies in logs or API errors.
                prefs().edit().putString("sync_status", "Offline or sync failed; retry pending (" + e.javaClass.simpleName + ")").apply()
                changed()
                false
            }
        }
    }

    suspend fun isCurrent(card: com.ichi2.anki.libanki.Card): Boolean {
        if (!enabled()) return true
        // Validate against the current local collection. Never perform network
        // IO on the reviewer answer path.
        return withCol {
            val latest = getCard(card.id)
            latest.reps == card.reps && latest.mod == card.mod && latest.queue == card.queue && latest.due == card.due
        }
    }

    suspend fun beforeReview() {
        if (!enabled()) return
        changed()
        // Remote native sync happens in the background; do not block rendering.
        withCol {
            val parentId = prefs().getString("parent_deck_id", "")?.toLongOrNull() ?: return@withCol
            val tree = sched.deckDueTree()
            val nodes = tree.toList()
            val parent = nodes.firstOrNull { it.did == parentId } ?: return@withCol
            val current = nodes.firstOrNull { it.did == decks.selected() } ?: return@withCol
            if (current.did != parent.did && !current.fullDeckName.startsWith(parent.fullDeckName + "::")) return@withCol
            fun eligible(node: com.ichi2.anki.libanki.sched.DeckNode) =
                node.newCount > 0 || (prefs().getString("clearance", "") != "new_only" && node.revCount + node.lrnCount > 0)
            if (!eligible(current)) {
                // Anki's tree is already ordered by deck name. Numeric-aware
                // comparison matches the companion's subdeck ordering.
                fun natural(name: String) = Regex("[0-9]+").replace(name.lowercase()) { it.value.padStart(20, '0') }
                val next = parent.children.sortedBy { natural(it.fullDeckName) }.firstOrNull { eligible(it) }
                if (next != null) decks.select(next.did)
            }
        }
    }

    fun history(uri: Uri): MatrixCursor = runBlocking {
        val since = uri.getQueryParameter("since")?.toLongOrNull()?.coerceAtLeast(0) ?: 0
        val limit = (uri.getQueryParameter("limit")?.toIntOrNull() ?: 1000).coerceIn(1, 1000)
        withCol {
            val result = MatrixCursor(arrayOf("id", "cid", "time", "ease", "ivl", "lastIvl"))
            val ids = uri.getQueryParameter("ids")?.split(",")?.map { it.toLong() }
            require(ids == null || ids.size in 1..300)
            val cursor = if (ids == null) db.query("SELECT id,cid,time,ease,ivl,lastIvl FROM revlog WHERE id>=? AND ease>0 ORDER BY id LIMIT ?", since, limit)
                else db.query("SELECT id,cid,time,ease,ivl,lastIvl FROM revlog WHERE ease>0 AND id IN (" + ids.joinToString(",") { "?" } + ")", *ids.toTypedArray())
            cursor.use {
                while (it.moveToNext()) result.addRow(arrayOf<Any>(it.getLong(0), it.getLong(1), it.getInt(2), it.getInt(3), it.getInt(4), it.getInt(5)))
            }
            result
        }
    }
}
