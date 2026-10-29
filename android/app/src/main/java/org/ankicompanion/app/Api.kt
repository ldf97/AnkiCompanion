package org.ankicompanion.app

import org.json.JSONObject
import java.net.URL
import java.net.HttpURLConnection
import java.io.File
import java.security.MessageDigest

class Api(private val config:JSONObject) {
    companion object {
        fun validate(url:String,allowLan:Boolean) {
            val u=URL(url);require(u.protocol in listOf("http","https") && u.userInfo==null && u.query==null && u.ref==null){"Use an HTTPS server URL"}
            val host=u.host.lowercase();val loopback=host in listOf("localhost","127.0.0.1","[::1]","::1")
            val local=host.startsWith("10.") || host.startsWith("192.168.") || Regex("172\\.(1[6-9]|2[0-9]|3[01])\\..+").matches(host) || host.endsWith(".local")
            require(u.protocol=="https" || loopback || (allowLan && local)){"HTTPS required; trusted LAN HTTP needs opt-in"}
        }
    }
    private fun open(path:String,method:String="GET",type:String="application/json"):HttpURLConnection {
        val base=config.getString("url").trimEnd('/');validate(base,config.optBoolean("allow_lan_http"))
        return (URL(base+path).openConnection() as HttpURLConnection).apply {
            requestMethod=method;connectTimeout=15000;readTimeout=30000;instanceFollowRedirects=false
            setRequestProperty("Authorization","Bearer "+config.getString("token"));setRequestProperty("Content-Type",type)
        }
    }
    fun bytes(path:String,method:String="GET",body:ByteArray?=null,type:String="application/json"):ByteArray {
        val c=open(path,method,type)
        try {
            if(body!=null){c.doOutput=true;c.setFixedLengthStreamingMode(body.size);c.outputStream.use{it.write(body)}}
            if(c.responseCode !in 200..299)throw IllegalStateException("Server ${c.responseCode}: "+(c.errorStream?.bufferedReader()?.use{it.readText().take(200)} ?: "request rejected"))
            return c.inputStream.use { stream ->
                val output=java.io.ByteArrayOutputStream();val buffer=ByteArray(65536);var total=0
                while(true){val n=stream.read(buffer);if(n<0)break;total+=n;require(total<=52*1024*1024){"Response too large"};output.write(buffer,0,n)}
                output.toByteArray()
            }
        } finally {c.disconnect()}
    }
    fun json(path:String,method:String="GET",body:JSONObject?=null):JSONObject = JSONObject(String(bytes(path,method,body?.toString()?.toByteArray(Charsets.UTF_8)),Charsets.UTF_8))
    fun download(path:String,destination:File,expectedSha:String,maxBytes:Long=500L*1024*1024) {
        val c=open(path);val digest=MessageDigest.getInstance("SHA-256");val temp=File(destination.path+".tmp")
        try {
            require(c.responseCode==200){"Download rejected: ${c.responseCode}"};destination.parentFile?.mkdirs()
            var total=0L
            c.inputStream.use { input -> temp.outputStream().use { output ->
                val buffer=ByteArray(65536)
                while(true){val n=input.read(buffer);if(n<0)break;total+=n;require(total<=maxBytes){"Download too large"};digest.update(buffer,0,n);output.write(buffer,0,n)}
            }}
            val actual=digest.digest().joinToString(""){"%02x".format(it)}
            require(actual==expectedSha.lowercase()){ "Update checksum did not match" };check(temp.renameTo(destination))
        } finally {c.disconnect();temp.delete()}
    }
}
