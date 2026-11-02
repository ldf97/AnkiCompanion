package org.ankicompanion.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import java.io.File
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PortabilityTest {
    @Test fun encryptedRecoveryContainsOriginalPrivateSkinAndRestoresExactBytes() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val file=File(context.filesDir,"packs/recovery_test/1.0.0/original.png")
        check(file.parentFile!!.mkdirs() || file.parentFile!!.isDirectory)
        val original=byteArrayOf(0,1,2,3,4,5,6,7,8,9,10)
        file.writeBytes(original)
        val encrypted=Portability.exportToBytes(context,"original skin passphrase 2026")
        assertFalse(String(encrypted).contains("original.png"))
        assertTrue(file.delete())
        Portability.restoreFromBytes(context,encrypted,"original skin passphrase 2026")
        assertArrayEquals(original,file.readBytes())
    }

    @Test fun encryptedRecoveryRoundTripAndWrongPasswordCannotRestore() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val storage=Storage(context)
        storage.saveConnection(JSONObject().put("url","https://example.org")
            .put("token","test-token-very-long-0123456789")
            .put("collection_id","primary"))
        storage.setSetting("history_cursor","1234567")
        val before=storage.deviceId
        val secret="A secure recovery phrase 2026"
        val encrypted=Portability.exportToBytes(context,secret)
        assertFalse(String(encrypted).contains("test-token-very-long-0123456789"))
        try {
            Portability.restoreFromBytes(context,encrypted,"wrong password for recovery")
            fail("Recovery must reject the wrong password")
        } catch(expected:javax.crypto.AEADBadTagException) { }
        assertEquals(0,Portability.restoreFromBytes(context,encrypted,secret))
        assertEquals(before,storage.deviceId)
        assertEquals("1234567",storage.getSetting("history_cursor"))
        assertEquals("test-token-very-long-0123456789",storage.connection()!!.getString("token"))
    }
}
