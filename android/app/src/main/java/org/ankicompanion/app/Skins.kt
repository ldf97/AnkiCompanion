package org.ankicompanion.app

import android.content.Context
import android.graphics.BitmapFactory
import org.json.JSONObject
import java.io.File
import java.io.ByteArrayInputStream
import java.util.zip.ZipInputStream
import java.util.UUID

class Skins(context:Context) {
    val base=File(context.filesDir,"skins").apply{mkdirs()}
    private fun safe(value:String):String {
        require(value.isNotBlank() && !value.startsWith('/') && !value.contains('\\') && !value.contains('\u0000') && value.split('/').none{it in listOf("..",".","")}){"Unsafe skin path"}
        return value
    }
    fun directory(id:String,version:String):File {
        require(Regex("[a-z][a-z0-9_-]{1,45}").matches(id) && Regex("[A-Za-z0-9][A-Za-z0-9_.-]{0,39}").matches(version)){"Invalid skin ID/version"}
        return File(File(base,id),version)
    }
    fun manifest(root:File)=JSONObject(File(root,"skin.json").readText())
    fun ensure(api:Api,id:String,version:String):File {
        val dest=directory(id,version)
        if(File(dest,"skin.json").isFile)return dest
        return install(api.bytes("/v1/skins/$id/$version/pack.zip"),id,version)
    }
    @Synchronized fun install(bytes:ByteArray,expectedId:String?=null,expectedVersion:String?=null):File {
        require(bytes.size<=50*1024*1024){"Skin exceeds 50 MiB"}
        val temp=File(base,"staging-"+UUID.randomUUID()).apply{mkdirs()}
        try {
            val names=mutableSetOf<String>();var count=0;var total=0L
            ZipInputStream(ByteArrayInputStream(bytes)).use {zip ->
                while(true) {
                    val entry=zip.nextEntry ?: break
                    require(++count<=140){"Too many skin files"}
                    val path=safe(entry.name.trimEnd('/'));require(names.add(path.lowercase())){"Duplicate skin path"}
                    if(entry.isDirectory){zip.closeEntry();continue}
                    val file=File(temp,path);require(file.extension.lowercase() in listOf("json","png","jpg","jpeg","webp","svg")){"Unsupported file type"}
                    file.parentFile?.mkdirs()
                    file.outputStream().use {output ->
                        val buffer=ByteArray(65536)
                        while(true){val n=zip.read(buffer);if(n<0)break;total+=n;require(total<=100L*1024*1024){"Expanded skin too large"};output.write(buffer,0,n)}
                    };zip.closeEntry()
                }
            }
            require(File(temp,"skin.json").length() in 1..200000){"Invalid skin manifest"}
            val skin=manifest(temp);val id=skin.getString("id");val version=skin.getString("version")
            val dest=directory(id,version)
            require(expectedId==null || id==expectedId);require(expectedVersion==null || version==expectedVersion)
            require(!dest.exists()){"Skin version already installed"};validate(temp,skin)
            dest.parentFile?.mkdirs();check(temp.renameTo(dest)){"Cannot install skin"};return dest
        } finally {temp.deleteRecursively()}
    }
    private fun validate(root:File,skin:JSONObject) {
        require(skin.getInt("schema_version")==1)
        val canvas=skin.getJSONObject("canvas");require(canvas.getInt("width")==1100 && canvas.getInt("height")==468)
        fun media(path:String,icon:Boolean=false) {
            val file=File(root,safe(path));require(file.isFile){"Missing $path"}
            if(file.extension.lowercase()=="svg") {
                require(icon && file.length()<=100000)
                val xml=file.readText()
                require(!Regex("<!DOCTYPE|<!ENTITY|(?:href|style|on[a-z]+)\\s*=",RegexOption.IGNORE_CASE).containsMatchIn(xml)){"Unsafe SVG"}
                val allowed=setOf("svg","title","defs","linearGradient","radialGradient","stop","path","rect","circle","ellipse","g")
                Regex("<\\s*/?\\s*([A-Za-z][A-Za-z0-9]*)").findAll(xml).forEach{require(it.groupValues[1] in allowed){"Unsupported SVG element"}}
                Regex("url\\(([^)]*)\\)",RegexOption.IGNORE_CASE).findAll(xml).forEach{require(Regex("#[A-Za-z0-9_-]+").matches(it.groupValues[1]))}
            } else {
                require(file.extension.lowercase() in listOf("png","jpg","jpeg","webp"))
                val opts=BitmapFactory.Options().apply{inJustDecodeBounds=true};BitmapFactory.decodeFile(file.path,opts)
                require(opts.outWidth in 1..8192 && opts.outHeight in 1..8192 && opts.outWidth.toLong()*opts.outHeight<=30000000){"Invalid image dimensions"}
            }
        }
        val pools=skin.getJSONObject("background_pools")
        pools.keys().forEach {key -> val a=pools.getJSONArray(key);require(a.length()>0);for(i in 0 until a.length())media(a.getString(i))}
        var previous=0;val ids=mutableSetOf<String>()
        for(s in skin.getJSONArray("time_slots").objects()) {
            require(s.getInt("start_minute")==previous);previous=s.getInt("end_minute");require(previous in 1..1440)
        };require(previous==1440)
        for(slot in skin.getJSONArray("time_slots").objects()+skin.getJSONObject("completion")) {
            require(ids.add(slot.getString("id")))
            val portraits=slot.getJSONArray("portraits");require(portraits.length()>0);for(i in 0 until portraits.length())media(portraits.getString(i))
            val quotes=slot.getJSONArray("quotes");require(quotes.length()>0);quotes.objects().forEach{require(it.getString("text").length in 1..1000)}
            val bg=slot.getJSONObject("background")
            when(bg.getString("mode")){"none"->Unit;"fixed"->media(bg.getString("asset"));"shared","random"->require(pools.has(bg.getString("pool")));else->error("Invalid background")}
        }
        require(skin.getJSONObject("completion").getJSONObject("background").getString("mode")=="none")
        val style=skin.getJSONObject("style");require(style.getDouble("max_red_tint") in 0.0..1.0)
        require(style.getInt("red_tint_start_minute") in 0..1438 && style.getInt("red_tint_end_minute") in (style.getInt("red_tint_start_minute")+1)..1439)
        val icons=style.getJSONObject("icons");for(name in listOf("flame_lit","flame_unlit","warning_badge"))media(icons.getString(name),true)
    }
}
