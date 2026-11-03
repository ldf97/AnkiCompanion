package org.ankicompanion.app

import android.content.Intent
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * End-to-end Update control test on a real Android emulator.
 *
 * A temporary host-loopback HTTP server offers the next same-signer APK.
 * The app uses its real button, manifest parsing, streaming SHA-256 verification,
 * APK package/signer/version validation, and launches Android's system installer.
 * The CI runner confirms the OS installation and retained private data afterward.
 */
@RunWith(AndroidJUnit4::class)
class UpdateButtonClickTest {
    private val inst get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = inst.targetContext

    private fun findUpdateButton(root:View): Button? {
        if(root is Button && root.text.toString().startsWith("App updates")) return root
        if(root is ViewGroup) {
            for(i in 0 until root.childCount) {
                val result=findUpdateButton(root.getChildAt(i))
                if(result!=null)return result
            }
        }
        return null
    }

    @Test fun clickUpdateDownloadsAndOpensSystemInstaller() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("update_button_phase")=="run")
        assertEquals("Run the baseline 0.1.1 APK first","0.1.1",BuildConfig.VERSION_NAME)
        UpdateAcceptanceTransport.manifestUrl="http://10.0.2.2:8767/update.json"
        UpdateAcceptanceTransport.assetUrl="http://10.0.2.2:8767/app-patched.apk"

        val device=UiDevice.getInstance(inst)
        val activity=inst.startActivitySync(Intent(context,MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)) as MainActivity
        inst.waitForIdleSync()
        var clicked=false
        inst.runOnMainSync {
            val button=findUpdateButton(activity.window.decorView)
            assertNotNull("The Android app must expose its Update button",button)
            clicked=button!!.performClick()
        }
        assertTrue("The real Android Update button was not clicked",clicked)

        assertTrue("Click did not fetch the next release and display confirmation",
            device.wait(Until.hasObject(By.text("Update to 0.1.2")),90000))
        // AOSP renders AlertDialog actions as "UPDATE" on some API levels.
        // The system resource id is more stable than case-sensitive text.
        val positive=device.wait(Until.findObject(By.res("android:id/button1")),10000)
            ?: device.findObject(By.text(java.util.regex.Pattern.compile("(?i)^update$")))
        assertNotNull("No Update confirmation button",positive)
        positive.click()

        val staged=File(context.filesDir,"updates/companion-update.apk")
        val end=System.currentTimeMillis()+90000
        while(System.currentTimeMillis()<end && (!staged.isFile || staged.length()<1000000L)) {
            Thread.sleep(250)
        }
        assertTrue("The Update button did not download a complete APK",staged.isFile && staged.length()>1000000L)
        // MainActivity invokes Updates.install, which must open Android's package
        // installer or its explicit install-permission screen. The host runner
        // then accepts the OS dialog and verifies the new installed version.
        var target=""
        val timeLimit=System.currentTimeMillis()+30000
        while(System.currentTimeMillis()<timeLimit) {
            target=device.currentPackageName ?: ""
            if(target.isNotBlank() && target!=context.packageName && !target.contains("launcher")) break
            Thread.sleep(350)
        }
        assertTrue("Update never opened the Android package installer; foreground=$target",
            target.isNotBlank() && target!=context.packageName && !target.contains("launcher"))

        File(context.getExternalFilesDir(null),"update-button-acceptance.json")
            .writeText("""{"clicked":true,"manifest":"0.1.2","apk_downloaded":true,"installer_opened":true,"foreground":"$target"}""")
    }
}
