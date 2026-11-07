package org.ankicompanion.app

import org.json.JSONObject
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SyncTraceTest {
    @Test fun redactsPairingTokensAndAuthorization() {
        val token="testingsecretpairingtoken123"
        val configuration=JSONObject().put("token",token)
        val message="Request rejected: token=$token Authorization: Bearer $token"
        val safe=SyncTrace.redact(message,configuration)
        assertFalse(safe.contains(token))
        assertTrue(safe.contains("[REDACTED]"))
    }
}
