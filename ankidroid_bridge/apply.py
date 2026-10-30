"""Apply the auditable bridge overlay to one exact upstream AnkiDroid commit."""
from pathlib import Path
import argparse, shutil, subprocess

PIN='d9bf072f814a0c37d30a694192593b31ff2df875'
def apply(root):
    root=Path(root).resolve();overlay=Path(__file__).resolve().parent
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if sha!=PIN:raise SystemExit('Expected AnkiDroid v2.25.3 at '+PIN+', got '+sha)
    marker=root/'.companion-overlay-applied'
    if marker.exists():raise SystemExit('Overlay already applied; start from a clean pinned checkout')
    def edit(path,old,new):
        p=root/path;s=p.read_text()
        if s.count(old)!=1:raise RuntimeError(f'Expected exactly one patch target in {path}: {old[:80]}')
        p.write_text(s.replace(old,new))
    base='AnkiDroid/src/main/java/com/ichi2/anki/'
    shutil.copy2(overlay/'CompanionIntegration.kt',root/base/'CompanionIntegration.kt')
    edit('AnkiDroid/build.gradle','applicationId = "com.ichi2.anki"','applicationId = "com.ichi2.anki.companion"')
    edit('AnkiDroid/build.gradle','resValue "string", "app_name", "AnkiDroid"','resValue "string", "app_name", "AnkiDroid Companion"')
    api=root/'api/build.gradle.kts';api.write_text(api.read_text().replace('com.ichi2.anki.permission.READ_WRITE_DATABASE','com.ichi2.anki.companion.permission.READ_WRITE_DATABASE').replace('com.ichi2.anki.flashcards','com.ichi2.anki.companion.flashcards').replace('com.ichi2.anki.debug.permission','com.ichi2.anki.companion.debug.permission').replace('com.ichi2.anki.debug.flashcards','com.ichi2.anki.companion.debug.flashcards'))
    edit(base+'AnkiDroidApp.kt','        initializeNavigator()','        initializeNavigator()\n        CompanionIntegration.initialize(this)')
    edit(base+'AnkiActivity.kt','        Analytics.sendAnalyticsScreenView(analyticsScreenName)','        CompanionIntegration.requestSync()\n        Analytics.sendAnalyticsScreenView(analyticsScreenName)')
    edit(base+'AnkiActivity.kt','        customTabActivityHelper.unbindCustomTabsService(this)','        CompanionIntegration.requestSync()\n        customTabActivityHelper.unbindCustomTabsService(this)')
    vm=base+'ui/windows/reviewer/ReviewerViewModel.kt'
    edit(vm,'        Timber.v("ReviewerViewModel::updateCurrentCard")','        Timber.v("ReviewerViewModel::updateCurrentCard")\n        com.ichi2.anki.CompanionIntegration.beforeReview()')
    edit(vm,'        val state = queueState.await() ?: return\n        val card = currentCard.await()','''        val state = queueState.await() ?: return
        val card = currentCard.await()
        if (!com.ichi2.anki.CompanionIntegration.isCurrent(card)) {
            updateCurrentCard()
            return
        }''')
    edit(vm,'        actionFeedbackFlow.emit(tryUndo())','        actionFeedbackFlow.emit(tryUndo())\n        com.ichi2.anki.CompanionIntegration.changed()\n        com.ichi2.anki.CompanionIntegration.requestSync()')
    edit(vm,'        actionFeedbackFlow.emit(tryRedo())','        actionFeedbackFlow.emit(tryRedo())\n        com.ichi2.anki.CompanionIntegration.changed()\n        com.ichi2.anki.CompanionIntegration.requestSync()')
    provider=base+'provider/CardContentProvider.kt'
    edit(provider,'        val col = getColUnsafe()\n        Timber.d(getLogMessage("query", uri))','''        if (uri.path == "/companion_revlog") return com.ichi2.anki.CompanionIntegration.history(uri)
        val col = getColUnsafe()
        Timber.d(getLogMessage("query", uri))''')
    edit(provider,'    override fun onCreate(): Boolean {','''    override fun call(method: String, arg: String?, extras: android.os.Bundle?): android.os.Bundle? {
        if (!method.startsWith("companion.")) return super.call(method, arg, extras)
        if (!hasReadWritePermission()) throw SecurityException("AnkiDroid read/write permission required")
        com.ichi2.anki.CompanionIntegration.initialize(context!!)
        return when (method) {
            "companion.capabilities" -> com.ichi2.anki.CompanionIntegration.status()
            "companion.configure" -> com.ichi2.anki.CompanionIntegration.configure(context!!, extras ?: android.os.Bundle())
            "companion.sync" -> com.ichi2.anki.CompanionIntegration.requestSync()
            else -> throw IllegalArgumentException("Unknown companion method")
        }
    }

    override fun onCreate(): Boolean {''')
    marker.write_text(PIN+'\n')
    print('Applied companion provider and native-sync hooks to pinned AnkiDroid '+PIN)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('checkout');apply(p.parse_args().checkout)
