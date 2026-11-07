package org.ankicompanion.app

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL
import java.time.Instant

/** Read-only connection tests and the app's own recent sync trace. */
object Diagnostics {
    fun collect(context:Context):String {
        val store=Storage(context)
        val config=store.connection()
        val lines=mutableListOf<String>()
        fun line(value:String) { lines.add(SyncTrace.redact(value,config)) }
        fun attempt(name:String,work:()->Unit) {
            val start=System.currentTimeMillis()
            try {
                work()
                line("$name: completed in ${System.currentTimeMillis()-start}ms")
            }catch(e:Exception) {
                line("$name: ${e.javaClass.simpleName}: ${e.message ?: "No details"} (${System.currentTimeMillis()-start}ms)")
            }
        }
        val now=System.currentTimeMillis()
        line("Anki Companion Diagnostics")
        line("Generated UTC: ${Instant.ofEpochMilli(now)}")
        line("Version: ${BuildConfig.VERSION_NAME} (build ${BuildConfig.VERSION_CODE})")
        line("Android: API ${android.os.Build.VERSION.SDK_INT}")
        line("Connection configured: ${config!=null}")
        line("Device ID: ${store.deviceId}")
        line("Last sync stage: ${store.getSetting("sync_stage","not recorded")}")
        line("Last sync error: ${store.getSetting("sync_error","none").ifBlank{"none"}}")
        line("Bridge status: ${store.getSetting("bridge_status","not recorded")}")
        line("FCM status: ${store.getSetting("fcm_status","not recorded")}")
        val cached=store.load("state.json")
        if(cached!=null) {
            val age=(now-cached.optLong("server_time_ms",0)).coerceAtLeast(0)/1000
            line("Cached server state: ${age}s old; date=${cached.optString("date","unknown")}; server streak=${cached.optInt("streak",-1)}")
            line("Cached local pending: ${cached.optInt("locally_pending",-1)}")
        } else line("Cached server state: not available")
        attempt("Local queue (read only)") {
            Outbox(context).use { out ->
                val query="SELECT COUNT(*), SUM(CASE WHEN sent=0 THEN 1 ELSE 0 END), SUM(CASE WHEN undone=1 AND undo_sent=0 THEN 1 ELSE 0 END) FROM events"
                out.readableDatabase.rawQuery(query,null).use { c ->
                    if(c.moveToFirst())line("Local review queue: ${c.getLong(0)} total; ${c.getLong(1)} unsent; ${c.getLong(2)} retractions pending")
                }
            }
        }
        val network=context.getSystemService(ConnectivityManager::class.java)
        val capabilities=network.activeNetwork?.let { network.getNetworkCapabilities(it) }
        line("Android network: present=${network.activeNetwork!=null}; internet=${capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)==true}; validated=${capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)==true}")

        if(config!=null) {
            val raw=config.optString("url","")
            attempt("Server URL validation") {
                Api.validate(raw,config.optBoolean("allow_lan_http",false))
                val parsed=URL(raw)
                line("Configured endpoint: ${parsed.protocol}://${parsed.host}${if(parsed.port>0)":${parsed.port}" else ""} (path omitted)")
                line("Collection ID: ${config.optString("collection_id","primary")}")
            }
            val parsed=try { URL(raw) }catch(_:Exception){null}
            if(parsed!=null) {
                attempt("DNS lookup") {
                    val resolved=InetAddress.getAllByName(parsed.host)
                    line("DNS: resolved ${resolved.size} address(es)")
                }
                fun request(name:String,path:String,authorized:Boolean) {
                    attempt(name) {
                        val connection=(URL(raw.trimEnd('/')+path).openConnection() as HttpURLConnection)
                        try {
                            connection.requestMethod="GET"
                            connection.connectTimeout=8000
                            connection.readTimeout=12000
                            connection.instanceFollowRedirects=false
                            if(authorized)connection.setRequestProperty("Authorization","Bearer "+config.getString("token"))
                            val status=connection.responseCode
                            line("$name HTTP status: $status")
                            if(status !in 200..299) {
                                line("$name failed: HTTP $status (response content suppressed)")
                            }
                        }finally {connection.disconnect()}
                    }
                }
                request("Public server health /health","/health",false)
                val device=java.net.URLEncoder.encode(store.deviceId,"UTF-8")
                val collection=java.net.URLEncoder.encode(config.optString("collection_id","primary"),"UTF-8")
                request("Authenticated state /v1/state","/v1/state?device_id=$device&collection_id=$collection",true)
            }
        }
        attempt("AnkiDroid bridge capabilities") {
            line("AnkiDroid packages installed: ${AnkiBridge.installed(context).joinToString().ifBlank{"none"}}")
            line("Anki access granted: ${AnkiBridge.permitted(context)}")
            val info=AnkiBridge.capabilities(context)
            line("Bridge reachable: ${info!=null}")
            if(info!=null) {
                line("Reviewer active: ${info.getBoolean("reviewer_active")}")
                line("Native sync status: ${info.getString("sync_status","unknown")}")
                line("Native sync enabled: ${info.getBoolean("enabled")}")
            }
        }
        line("---- Recent app sync trace (most recent last) ----")
        val history=store.load("sync-trace.json")?.optJSONArray("events")
        if(history==null || history.length()==0)line("(No trace recorded by installed version)")
        else for(i in 0 until history.length()) {
            val event=history.optJSONObject(i) ?: continue
            val at=Instant.ofEpochMilli(event.optLong("at_ms",0)).toString()
            line("$at | ${event.optString("stage")} | ${event.optString("detail")}")
        }
        line("---- End diagnostics ----")
        return lines.joinToString("\n")
    }
}
