package com.ankicompanion.ponglab

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.MotionEvent
import android.view.View
import kotlin.math.max
import kotlin.math.min
import kotlin.random.Random

/** Standalone native Android Pong. No Anki components or services. */
class PongView(context: Context): View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val w = 640f
    private val h = 420f
    private var ballX = w/2
    private var ballY = h/2
    private var speedX = 4.0f
    private var speedY = 3.6f
    private var paddle = w/2
    private var ai = w/2
    private var playerPoints = 0
    private var aiPoints = 0
    private var ended = false
    init { setBackgroundColor(Color.rgb(13,24,46)) }

    private fun resetBall(){
        ballX=w/2; ballY=h/2
        speedX=if(Random.nextBoolean())4f else -4f
        speedY=if(Random.nextBoolean())3.6f else -3.6f
    }
    fun restart() {playerPoints=0;aiPoints=0;ended=false;resetBall();invalidate()}

    override fun onDraw(canvas: Canvas){
        super.onDraw(canvas)
        val sx=width/w; val sy=height/h
        canvas.save(); canvas.scale(sx,sy)
        paint.color=Color.rgb(27,50,87);paint.strokeWidth=2f
        canvas.drawLine(0f,h/2,w,h/2,paint)
        paint.color=Color.rgb(224,233,255);paint.textSize=38f;paint.textAlign=Paint.Align.CENTER
        canvas.drawText("$aiPoints  :  $playerPoints",w/2,206f,paint)
        val top=ai.coerceIn(57f,w-57f)
        val bottom=paddle.coerceIn(57f,w-57f)
        paint.color=Color.rgb(255,172,119)
        canvas.drawRoundRect(top-55f,30f,top+55f,43f,5f,5f,paint)
        paint.color=Color.rgb(154,242,221)
        canvas.drawRoundRect(bottom-55f,h-45f,bottom+55f,h-32f,5f,5f,paint)
        if(!ended){
            ballX+=speedX;ballY+=speedY
            if(ballX<=9f || ballX>=w-9f) speedX=-speedX
            ai=(ai+(ballX-ai).coerceIn(-3.5f,3.5f)).coerceIn(55f,w-55f)
            if(ballY<52f && speedY<0 && ballX in (top-63f)..(top+63f)) {
                speedY=-speedY;speedX+=(ballX-top)/32f
            }
            if(ballY>h-54f && speedY>0 && ballX in (bottom-63f)..(bottom+63f)) {
                speedY=-speedY;speedX+=(ballX-bottom)/28f
            }
            speedX=speedX.coerceIn(-7f,7f)
            if(ballY<0f){playerPoints++;resetBall()}
            if(ballY>h){aiPoints++;resetBall()}
            if(playerPoints==7 || aiPoints==7) ended=true
        }
        paint.color=Color.WHITE
        canvas.drawCircle(ballX,ballY,8f,paint)
        if(ended){
            paint.textSize=30f
            canvas.drawText(if(playerPoints>=7)"You win!" else "Computer wins!",w/2,h/2+58f,paint)
        }
        canvas.restore()
        if(!ended)postInvalidateDelayed(16)
    }
    override fun onTouchEvent(event:MotionEvent):Boolean {
        if(event.actionMasked==MotionEvent.ACTION_DOWN || event.actionMasked==MotionEvent.ACTION_MOVE){
            paddle=((event.x/width)*w).coerceIn(55f,w-55f)
            invalidate()
            return true
        }
        return true
    }
}
