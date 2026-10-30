package org.ankicompanion.app

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import org.json.JSONObject
import org.json.JSONArray

/** Discover an implemented provider; never assume stock AnkiDroid exposes review history. */
object AnkiBridge {
    private val packages=listOf("com.ichi2.anki.companion", "com.ichi2.anki.companion.debug", "com.ichi2.anki")
    fun installed(context:Context)=packages.filter {name->try {context.packageManager.getPackageInfo(name,0);true}catch(e:PackageManager.NameNotFoundException){false}}
    fun packageName(context:Context):String {
        val choices=installed(context);val selected=Storage(context).getSetting("anki_package")
        return selected.takeIf {it in choices} ?: choices.firstOrNull() ?: error("Install AnkiDroid Companion, then grant Anki access")
    }
    fun permission(context:Context)=packageName(context)+".permission.READ_WRITE_DATABASE"
    private fun root(context:Context)=Uri.parse("content://"+packageName(context)+".flashcards")
    fun permitted(context:Context)=try {context.checkSelfPermission(permission(context))==PackageManager.PERMISSION_GRANTED}catch(e:Exception){false}
    fun capabilities(context:Context):Bundle? = try {
        if(!permitted(context))null else context.contentResolver.call(root(context),"companion.capabilities",null,null)
            ?.takeIf {it.getInt("api_version")==1 && it.getBoolean("history") && it.getBoolean("native_sync")}
    }catch(e:Exception){null}
    fun decks(context:Context):List<JSONObject> {
        if(!permitted(context))return emptyList()
        val result=mutableListOf<JSONObject>()
        context.contentResolver.query(Uri.withAppendedPath(root(context),"decks"),arrayOf("deck_id","deck_name","deck_count"),null,null,null)?.use {cursor ->
            while(cursor.moveToNext()) {
                val counts=JSONArray(cursor.getString(cursor.getColumnIndexOrThrow("deck_count")))
                result.add(JSONObject().put("id",cursor.getLong(cursor.getColumnIndexOrThrow("deck_id")).toString())
                    .put("name",cursor.getString(cursor.getColumnIndexOrThrow("deck_name"))).put("learning",counts.getInt(0)).put("review",counts.getInt(1)).put("new",counts.getInt(2)))
            }
        };return result
    }
    fun refreshNative(context:Context) {
        val status=capabilities(context) ?: return
        if(status.getBoolean("enabled") && status.getString("sync_status")!="syncing" && System.currentTimeMillis()-status.getLong("synced_ms")>10000)
            context.contentResolver.call(root(context),"companion.sync",null,null)
    }
    fun nativeSync(context:Context) {
        context.startActivity(Intent("com.ichi2.anki.DO_SYNC").setPackage(packageName(context)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
    /** Blocking worker-only operation. A study command is not applied until native sync succeeds. */
    fun synchronize(context:Context) {
        val before=capabilities(context) ?: error("Automatic collection sync requires AnkiDroid Companion and Anki access")
        val generation=before.getLong("generation")
        context.contentResolver.call(root(context),"companion.sync",null,null)
        val deadline=SystemClock.elapsedRealtime()+60000
        while(SystemClock.elapsedRealtime()<deadline) {
            val now=capabilities(context) ?: error("AnkiDroid bridge became unavailable")
            if(now.getLong("generation")>generation && now.getString("sync_status")=="synced")return
            val status=now.getString("sync_status","")
            if(status.startsWith("Sign in") || status.startsWith("Initial/full") || status.startsWith("Offline"))error(status)
            Thread.sleep(250)
        }
        error("AnkiDroid sync did not finish in 60 seconds. Study request remains pending.")
    }
    fun history(context:Context,since:Long,ids:List<Long>?=null):List<JSONObject> {
        require(capabilities(context)!=null){"This AnkiDroid installation does not expose the companion history API"}
        val out=mutableListOf<JSONObject>()
        val builder=Uri.withAppendedPath(root(context),"companion_revlog").buildUpon().appendQueryParameter("since",since.toString())
        if(ids!=null)builder.appendQueryParameter("ids",ids.joinToString(","))
        val cursor=context.contentResolver.query(builder.build(),null,null,null,null) ?: error("AnkiDroid review history is unavailable")
        cursor.use {c->while(c.moveToNext())out.add(JSONObject().put("revlog_id",c.getLong(c.getColumnIndexOrThrow("id")))
            .put("card_id",c.getLong(c.getColumnIndexOrThrow("cid"))).put("duration_ms",c.getInt(c.getColumnIndexOrThrow("time")).coerceIn(0,600000)))}
        return out
    }
    fun configure(context:Context,settings:JSONObject):Boolean {
        if(capabilities(context)==null)return false
        val options=Bundle().apply {
            putBoolean("enabled",true);putString("parent_deck_id",settings.getString("parent_deck_id"));putString("clearance",settings.getString("clearance"))
        }
        return context.contentResolver.call(root(context),"companion.configure",null,options)?.getBoolean("enabled")==true
    }
    fun open(context:Context,deckId:String) {
        context.startActivity(Intent(Intent.ACTION_VIEW).setClassName(packageName(context),"com.ichi2.anki.IntentHandler")
            .putExtra("EXTRA_DECK_ID",deckId.toLong()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
