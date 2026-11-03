package org.ankicompanion.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.firebase.FirebaseApp
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

/** Catches APKs accidentally built without the owner's FCM client config. */
@RunWith(AndroidJUnit4::class)
class FirebaseConfigIntegrationTest {
    @Test fun firebaseClientIsEnabledInInstalledAndroidApplication() {
        val appContext=InstrumentationRegistry.getInstrumentation().targetContext
        val apps=FirebaseApp.getApps(appContext)
        assertFalse("Firebase missing: FCM will not receive notifications",apps.isEmpty())
        val options=FirebaseApp.getInstance().options
        assertEquals("ankicompanion",options.projectId)
        assertEquals("899490092033",options.gcmSenderId)
        assertEquals("org.ankicompanion.app",appContext.packageName)
    }
}
