package org.ankicompanion.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

/** Native undo removes a scheduling effect; never erases a real study attempt. */
@RunWith(AndroidJUnit4::class)
class UndoAccountabilityTest {
    private val target get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun undoneReviewStillCountsTowardDailyActivityAndStreak() {
        // Unique physical SQLite database: never inspect or mutate the app's
        // regular reviews.db, even when this test runs on an owner's emulator.
        val databaseName="companion-undo-test-${UUID.randomUUID()}.db"
        val now=System.currentTimeMillis()
        val id="primary:${now-2000}:12"
        val answer=JSONObject().put("collection_id","primary")
            .put("revlog_id",now-2000).put("card_id",12)
            .put("duration_ms",30000).put("rating",3)
        val entry=JSONObject().put("id",id).put("payload",answer)
            .put("timestamp",now-2000).put("sent",1)
            .put("undone",1).put("undo_sent",0)
        val settings=JSONObject().put("timezone","UTC").put("rollover_minute",0)
            .put("lesson_answers",1).put("lesson_ms",30000)
        val today=Rules.day(now,"UTC",0)
        val server=JSONObject().put("settings",settings).put("date",today)
            .put("policy",settings).put("today_events",JSONArray())
            .put("completed",false).put("streak",0)
            .put("progress",JSONObject().put("answers",0).put("duration_ms",0))
        try {
            Outbox(target,databaseName).use { out ->
                out.restoreTransfer(JSONArray().put(entry))
                val provisional=out.overlay(server)
                assertEquals(1,provisional.getJSONObject("progress").getInt("answers"))
                assertEquals(30000,provisional.getJSONObject("progress").getInt("duration_ms"))
                assertTrue(provisional.getBoolean("completed"))
                assertEquals(1,provisional.getInt("streak"))
                assertEquals(1,provisional.getInt("locally_pending"))
                // Upload retries/restore attempts do not create additional study credit.
                out.restoreTransfer(JSONArray().put(entry))
                assertEquals(1,out.overlay(server).getJSONObject("progress").getInt("answers"))
            }
        } finally {
            target.deleteDatabase(databaseName)
        }
    }
}
