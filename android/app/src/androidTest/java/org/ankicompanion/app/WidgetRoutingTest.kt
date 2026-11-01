package org.ankicompanion.app

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Verify widget tap targets the exact saved AnkiDroid deck without an app/sync detour. */
@RunWith(AndroidJUnit4::class)
class WidgetRoutingTest {
    private val target="com.ichi2.anki.companion.debug"

    @Test fun widgetTapLaunchesSavedEicosanoidsDeckDirectly() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val settings=JSONObject().put("parent_deck_id","987654321")
        val state=JSONObject().put("settings",settings)
        val launch=CompanionWidget.widgetIntent(context,state,target)
        assertEquals(Intent.ACTION_MAIN,launch.action)
        assertEquals(target,launch.component?.packageName)
        assertEquals("com.ichi2.anki.IntentHandler",launch.component?.className)
        assertEquals(987654321L,launch.getLongExtra("EXTRA_DECK_ID",-1))
        assertFalse("Widget must not wait for companion app native sync",launch.hasExtra("study"))
    }

    @Test fun widgetTapPrefersNextEligibleEicosanoidsChildDeckOverParent() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val phoneId=Storage(context).deviceId
        val state=JSONObject().put("settings",JSONObject().put("parent_deck_id","42"))
            .put("next_decks",JSONObject().put(phoneId,
                JSONObject().put("id","987654321").put("name","M2::Eicosanoids")))
        val launch=CompanionWidget.widgetIntent(context,state,target)
        assertEquals("com.ichi2.anki.IntentHandler",launch.component?.className)
        assertEquals(987654321L,launch.getLongExtra("EXTRA_DECK_ID",-1))
    }

    @Test fun widgetTapWithoutSelectedDeckExplainsSetupInsteadOfSilentlyDoingNothing() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val state=JSONObject().put("settings",JSONObject().put("parent_deck_id",""))
        val launch=CompanionWidget.widgetIntent(context,state,target)
        assertEquals(context.packageName,launch.component?.packageName)
        assertEquals(MainActivity::class.java.name,launch.component?.className)
        assertTrue(launch.getBooleanExtra("widget_setup",false))
        assertFalse(launch.hasExtra("study"))
    }

    @Test fun missingAnkiDroidOpensCompanionSetupNotBadIntent() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val state=JSONObject().put("settings",JSONObject().put("parent_deck_id","987654321"))
        // The fake package is explicitly absent; skip any actual external launch.
        val installed=AnkiBridge.installed(context)
        if(installed.isEmpty()) {
            val launch=CompanionWidget.widgetIntent(context,state)
            assertEquals(MainActivity::class.java.name,launch.component?.className)
            assertTrue(launch.getBooleanExtra("widget_setup",false))
        }
    }
}
