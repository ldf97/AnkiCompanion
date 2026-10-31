package org.ankicompanion.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.Color
import android.graphics.Typeface
import android.view.View
import android.widget.*
import android.text.InputType
import org.json.JSONObject
import java.io.File

class MainActivity:Activity() {
    private lateinit var storage:Storage
    private lateinit var scene:SceneView
    private lateinit var status:TextView
    private lateinit var progress:TextView
    private lateinit var bridge:TextView
    private lateinit var parent:Spinner
    private lateinit var mode:Spinner
    private lateinit var updateButton:Button
    private var state:JSONObject?=null
    private var decks=listOf<JSONObject>()
    private var renderedKey=""
    private var busy=false
    private var resumed=false
    private var pendingStudy=false
    private val handler=Handler(Looper.getMainLooper())
    private val ticker=object:Runnable {override fun run(){if(resumed){refresh();handler.postDelayed(this,5000)}}}
    private fun dp(value:Int)=(value*resources.displayMetrics.density).toInt()
    private fun text(value:String,size:Float=14f)=TextView(this).apply{text=value;textSize=size;setTextColor(Color.rgb(238,230,219));setPadding(0,dp(6),0,dp(6))}
    private fun button(label:String,action:()->Unit)=Button(this).apply{text=label;isAllCaps=false;setTextColor(Color.rgb(238,230,219));setOnClickListener{action()}}
    private fun api()=Api(storage.connection() ?: error("Connect a server first"))
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState);storage=Storage(this);pendingStudy=intent.getBooleanExtra("study",false)
        val scroll=ScrollView(this);val box=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(18),dp(16),dp(18),dp(18));setBackgroundColor(Color.rgb(18,20,24))};scroll.addView(box);setContentView(scroll)
        box.setOnApplyWindowInsetsListener {v,insets->v.setPadding(dp(18),dp(16)+insets.systemWindowInsetTop,dp(18),dp(18)+insets.systemWindowInsetBottom);insets}
        val head=LinearLayout(this);val title=text("ANKI / COMPANION",20f).apply{setTypeface(typeface,Typeface.BOLD)};head.addView(title,LinearLayout.LayoutParams(0,-2,1f));head.addView(button("Connect"){connect()});box.addView(head)
        scene=SceneView(this);box.addView(scene,LinearLayout.LayoutParams(-1,-2))
        status=text("Connect your companion server to begin.");box.addView(status)
        progress=text("No progress loaded");box.addView(progress)
        box.addView(text("Parent deck"));parent=Spinner(this);box.addView(parent)
        box.addView(text("Advance when"));mode=Spinner(this);mode.adapter=ArrayAdapter(this,android.R.layout.simple_spinner_dropdown_item,listOf("No new cards remaining","No new, review or due learning cards"));box.addView(mode)
        box.addView(button("Save deck settings"){saveDeck()})
        box.addView(button("Study next subdeck"){study()}.apply{setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(238,145,71)));setTextColor(Color.rgb(23,18,14))})
        val actions=LinearLayout(this);actions.addView(button("Anki access"){requestAnki()});actions.addView(button("Refresh"){refresh()});actions.addView(button("Sync AnkiDroid"){try{AnkiBridge.nativeSync(this)}catch(e:Exception){status.text=e.message}});box.addView(actions)
        val settings=LinearLayout(this);settings.addView(button("Lesson & day"){goals()});settings.addView(button("Skins"){skins()});box.addView(settings)
        updateButton=button("Updates · "+BuildConfig.VERSION_NAME){updates()};box.addView(updateButton)
        box.addView(button("Live widget updates"){LiveSyncService.start(this)})
        bridge=text("",12f);bridge.setTextColor(Color.rgb(160,164,173));box.addView(bridge)
        box.addView(text("A lesson maintains your streak. Anki decides which cards are available.",12f))
        Sync.schedule(this)
        storage.load("state.json")?.let{show(it)}
        if(intent.getBooleanExtra("updates",false))handler.post{updates()}
    }
    override fun onResume(){super.onResume();resumed=true;handler.removeCallbacks(ticker);handler.post(ticker)}
    override fun onPause(){resumed=false;handler.removeCallbacks(ticker);super.onPause()}
    private fun async(work:()->Any?,after:(Any?)->Unit={refresh()}) {
        Sync.executor.execute {
            try {val result=work();runOnUiThread{if(!isFinishing)after(result)}}
            catch(e:Exception){runOnUiThread{if(!isFinishing)status.text=e.message ?: "Action failed"}}
        }
    }
    private fun refresh() {
        if(busy || storage.connection()==null)return
        busy=true
        Sync.executor.execute {
            val value=try{Sync.run(applicationContext)}catch(e:Exception){null}
            runOnUiThread{busy=false;if(value!=null && !isFinishing){show(value);Commands.handle(this,api());if(pendingStudy){pendingStudy=false;study()}}}
        }
    }
    private fun show(value:JSONObject) {
        val first=state==null;state=value
        val error=storage.getSetting("sync_error")
        status.text=if(error.isEmpty())"Connected · "+value.getString("date") else "Offline · cached progress · "+value.getString("date")
        status.append(" · updated ${(System.currentTimeMillis()-value.getLong("server_time_ms"))/1000}s ago")
        val p=value.getJSONObject("progress");val goal=if(value.optString("local_day",value.getString("date"))==value.getString("date"))value.getJSONObject("policy") else value.getJSONObject("settings")
        progress.text="${p.getInt("answers")}/${goal.getInt("lesson_answers")} · ${minOf(100,p.getInt("answers")*100/goal.getInt("lesson_answers"))}% · ${maxOf(0,goal.getInt("lesson_answers")-p.getInt("answers"))} remaining · ${p.getInt("duration_ms")/1000} / ${goal.getInt("lesson_ms")/1000} active seconds · ${value.getInt("streak")} day streak"
        bridge.text=storage.getSetting("bridge_status")
        val line=value.getJSONObject("lineup");val key=line.toString()+value.getBoolean("completed")+value.getInt("streak")+System.currentTimeMillis()/60000
        if(key!=renderedKey) {
            async({Renderer(applicationContext).draw(value,Skins(applicationContext).directory(line.getString("skin_id"),line.getString("skin_version")))}){result->scene.frame=result as Frame;renderedKey=key}
        }
        val device=value.getJSONArray("devices").objects().firstOrNull{it.getString("device_id")==storage.deviceId}
        val latest=device?.getJSONArray("decks")?.objects() ?: emptyList()
        if(latest.map{it.getString("id")}!=decks.map{it.getString("id")}) {
            decks=latest;parent.adapter=ArrayAdapter(this,android.R.layout.simple_spinner_dropdown_item,decks.map{it.getString("name")})
            val index=decks.indexOfFirst{it.getString("id")==value.getJSONObject("settings").getString("parent_deck_id")};if(index>=0)parent.setSelection(index)
        } else decks=latest
        if(first)mode.setSelection(if(value.getJSONObject("settings").getString("clearance")=="new_only")0 else 1)
        val update=storage.load("update.json");updateButton.text=if(update?.optBoolean("available")==true)"Update to "+update.optString("version") else "Updates · "+BuildConfig.VERSION_NAME
    }
    private fun connect() {
        val old=storage.connection() ?: JSONObject();val box=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(20),0,dp(20),0)}
        val url=EditText(this).apply{hint="Paste pairing link from Windows";setText(old.optString("url"));inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI}
        val token=EditText(this).apply{hint="Pairing token";setText(old.optString("token"));inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD}
        val collection=EditText(this).apply{hint="Collection ID";setText(old.optString("collection_id","primary"))}
        val lan=CheckBox(this).apply{text="Allow HTTP on a trusted local network";isChecked=old.optBoolean("allow_lan_http")}
        for(view in listOf(url,token,collection,lan))box.addView(view)
        AlertDialog.Builder(this).setTitle("Companion server").setView(box).setNegativeButton("Cancel",null).setPositiveButton("Connect"){_,_->
            try {
                val pasted=url.text.toString().trim()
                val parsed=android.net.Uri.parse(pasted)
                // A single HTTPS URL carries the server address, token, and
                // collection ID. Existing manual connection fields still work.
                val embedded=if(parsed.scheme=="https")parsed.getQueryParameter("token") else null
                val serverUrl=if(embedded!=null)pasted.substringBefore('?').trimEnd('/') else pasted.trimEnd('/')
                val pairingToken=embedded ?: token.text.toString().trim()
                val pairingCollection=if(embedded!=null)parsed.getQueryParameter("collection_id") ?: "primary" else collection.text.toString()
                Api.validate(serverUrl,lan.isChecked)
                require(pairingToken.length>=16){"Invalid pairing link or token"}
                require(Regex("[A-Za-z0-9_-]{1,100}").matches(pairingCollection)){"Invalid collection ID"}
                storage.saveConnection(JSONObject().put("url",serverUrl).put("token",pairingToken).put("allow_lan_http",lan.isChecked).put("collection_id",pairingCollection))
                if(android.os.Build.VERSION.SDK_INT>=33)requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS),3)
                refresh()
            }catch(e:Exception){status.text=e.message}
        }.show()
    }
    private fun requestAnki() {
        try{requestPermissions(arrayOf(AnkiBridge.permission(this)),2)}
        catch(e:Exception){status.text="Install AnkiDroid Companion, then grant access here."}
    }
    private fun saveDeck() {
        val current=state ?: return;val selected=decks.getOrNull(parent.selectedItemPosition) ?: return
        val s=JSONObject(current.getJSONObject("settings").toString()).put("parent_deck_id",selected.getString("id")).put("clearance",if(mode.selectedItemPosition==0)"new_only" else "new_and_reviews")
        async({api().json("/v1/settings","PUT",s)})
    }
    private fun study() {
        val current=state ?: return
        if(!AnkiBridge.permitted(this)){requestAnki();return}
        val s=current.getJSONObject("settings")
        async({
            AnkiBridge.configure(applicationContext,s)
            AnkiBridge.synchronize(applicationContext)
            Rules.next(AnkiBridge.decks(applicationContext),s.getString("parent_deck_id"),s.getString("clearance"))
        }){result->
            val deck=result as? JSONObject
            if(deck==null)status.text="No eligible subdeck. Check your selected parent and Anki limits."
            else try{AnkiBridge.open(this,deck.getString("id"))}catch(e:Exception){status.text=e.message ?: "Could not open AnkiDroid"}
        }
    }
    private fun goals() {
        val current=state ?: return;val s=current.getJSONObject("settings");val box=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(20),0,dp(20),0)}
        val answers=EditText(this).apply{inputType=InputType.TYPE_CLASS_NUMBER;setText(s.getInt("lesson_answers").toString())}
        val seconds=EditText(this).apply{inputType=InputType.TYPE_CLASS_NUMBER;setText((s.getInt("lesson_ms")/1000).toString())}
        box.addView(text("Answered cards"));box.addView(answers);box.addView(text("Active seconds"));box.addView(seconds);box.addView(text("Changes apply to the next new study day. The initial 10 answers / 300 seconds is provisional.",12f))
        AlertDialog.Builder(this).setTitle("Daily lesson").setView(box).setNegativeButton("Cancel",null).setPositiveButton("Save"){_,_->
            try{val change=JSONObject(s.toString()).put("lesson_answers",answers.text.toString().toInt()).put("lesson_ms",seconds.text.toString().toInt()*1000);async({api().json("/v1/settings","PUT",change)})}catch(e:Exception){status.text="Enter valid numbers"}
        }.show()
    }
    private fun skins() {
        async({api().json("/v1/skins").getJSONArray("skins").objects()}){result->
            @Suppress("UNCHECKED_CAST") val available=result as List<JSONObject>
            AlertDialog.Builder(this).setTitle("Skin · applies immediately").setItems(available.map{it.getString("name")+" "+it.getString("version")}.toTypedArray()){_,index->
                val current=state ?: return@setItems;val chosen=available[index]
                val s=JSONObject(current.getJSONObject("settings").toString()).put("skin_id",chosen.getString("id")).put("skin_version",chosen.getString("version"));async({api().json("/v1/settings","PUT",s)})
            }.setNeutralButton("Import ZIP"){_,_->startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/zip").addCategory(Intent.CATEGORY_OPENABLE),10)}.setNegativeButton("Cancel",null).show()
        }
    }
    override fun onActivityResult(requestCode:Int,resultCode:Int,data:Intent?) {
        super.onActivityResult(requestCode,resultCode,data)
        if(requestCode==10 && resultCode==RESULT_OK && data?.data!=null) {
            val uri=data.data!!
            async({
                val bytes=contentResolver.openInputStream(uri)!!.use {input->val out=java.io.ByteArrayOutputStream();val b=ByteArray(65536);while(true){val n=input.read(b);if(n<0)break;require(out.size()+n<=50*1024*1024){"ZIP exceeds 50 MiB"};out.write(b,0,n)};out.toByteArray()}
                api().bytes("/v1/skins/import","POST",bytes,"application/zip")
            })
        }
    }
    private fun updates() {
        status.text="Checking GitHub release…"
        async({Updates.check(applicationContext,api(),true)}){result->
            val release=result as? JSONObject ?: return@async
            if(!release.optBoolean("available")){status.text=release.optString("message","No newer release");return@async}
            AlertDialog.Builder(this).setTitle("Update to "+release.getString("version")).setMessage(release.optString("notes")+"\nSource commit: "+release.optString("commit")).setNegativeButton("Later",null).setPositiveButton("Update"){_,_->
                status.text="Downloading and verifying update…"
                async({Updates.download(applicationContext,api(),release)}){file->Updates.install(this,file as File)}
            }.show()
        }
    }
}
