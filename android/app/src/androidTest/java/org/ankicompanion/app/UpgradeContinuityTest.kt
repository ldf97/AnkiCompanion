package org.ankicompanion.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Must be run in two distinct APK installations of the SAME package/signer:
 * seed under v1; adb install -r v2; verify without touching/restoring local data.
 * This tests Android Keystore, private art, settings and unsent review history.
 */
@RunWith(AndroidJUnit4::class)
class UpgradeContinuityTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun seedOriginalData() {
        val store=Storage(context)
        store.saveConnection(JSONObject()
            .put("url","https://example.org")
            .put("token","unchanged-private-test-token-012345")
            .put("collection_id","primary")
            .put("allow_lan_http",false))
        store.setSetting("history_cursor","1790000000000")
        store.setSetting("native_applied_revision","137")
        store.setSetting("upgrade_test_device_id",store.deviceId)
        store.save("state.json",JSONObject().put("marker","state-before-upgrade")
            .put("progress",JSONObject().put("answers",42)))
        val artwork=File(context.filesDir,"packs/private_eren/1.0.0/art.png")
        check(artwork.parentFile!!.mkdirs() || artwork.parentFile!!.isDirectory)
        artwork.writeBytes(byteArrayOf(1,2,3,4,5,6,7,8))
        val review=JSONObject().put("collection_id","primary")
            .put("revlog_id",1790000000111L).put("card_id",12)
            .put("duration_ms",4000).put("rating",3)
        val entry=JSONObject().put("id","primary:1790000000111:12")
            .put("payload",review).put("timestamp",1790000000111L)
            .put("sent",0).put("undone",0).put("undo_sent",0)
        Outbox(context).use{it.restoreTransfer(JSONArray().put(entry))}
        assertEquals(1,Outbox(context).use{it.exportTransfer().length()})
    }

    @Test fun verifyDataAfterInPlaceUpgrade() {
        val store=Storage(context)
        assertEquals("1790000000000",store.getSetting("history_cursor"))
        assertEquals("137",store.getSetting("native_applied_revision"))
        assertEquals(store.getSetting("upgrade_test_device_id"),store.deviceId)
        assertEquals("unchanged-private-test-token-012345",
            store.connection()!!.getString("token"))
        assertEquals("https://example.org",store.connection()!!.getString("url"))
        assertEquals("state-before-upgrade",store.load("state.json")!!.getString("marker"))
        assertEquals(42,store.load("state.json")!!.getJSONObject("progress").getInt("answers"))
        val bytes=File(context.filesDir,"packs/private_eren/1.0.0/art.png").readBytes()
        assertArrayEquals(byteArrayOf(1,2,3,4,5,6,7,8),bytes)
        val reviews=Outbox(context).use{it.exportTransfer()}
        assertEquals(1,reviews.length())
        assertEquals("primary:1790000000111:12",reviews.getJSONObject(0).getString("id"))
        assertEquals(0,reviews.getJSONObject(0).getInt("sent"))
        assertEquals(3,reviews.getJSONObject(0).getJSONObject("payload").getInt("rating"))
    }
}
