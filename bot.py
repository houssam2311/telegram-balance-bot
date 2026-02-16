import logging
import json
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
import firebase_admin
from firebase_admin import credentials, db

# ======================== ضع بياناتك هنا ========================
TOKEN = "8572697288:AAHPnY9hu7ktLrmsy1J_i3KWY5OoolOcxvY"  # Token بوتك
ADMIN_ID = 872300006                                         # ID الأدمن
FIREBASE_URL = "https://speed-recive-system-default-rtdb.europe-west1.firebasedatabase.app/"
cred = credentials.Certificate("serviceAccountKey.json")     # ملف Firebase
# =================================================================

# تهيئة Firebase
firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_URL
})

logging.basicConfig(level=logging.INFO)

AMOUNT, TIME = range(2)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)

    approved_ref = db.reference(f'users/approved/{user_id}')
    pending_ref = db.reference(f'users/pending/{user_id}')

    if approved_ref.get():
        await update.message.reply_text("مرحباً بك ✅\nاكتب تحقق لبدء عملية التحقق.")
        return ConversationHandler.END

    if pending_ref.get():
        await update.message.reply_text("طلبك قيد المراجعة ⏳")
        return ConversationHandler.END

    pending_ref.set({
        "name": user.first_name,
        "username": user.username,
    })

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"طلب تسجيل جديد\n\nID: {user_id}\nالاسم: {user.first_name}\n\n/approve {user_id}\n/reject {user_id}"
    )

    await update.message.reply_text("تم إرسال طلب التسجيل ✅")
    return ConversationHandler.END

# ================= APPROVE =================
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) == 0:
        await update.message.reply_text("ضع ID المستخدم بعد الأمر")
        return

    user_id = context.args[0]
    pending_ref = db.reference(f'users/pending/{user_id}')
    data = pending_ref.get()

    if not data:
        await update.message.reply_text("لا يوجد طلب بهذا ID")
        return

    db.reference(f'users/approved/{user_id}').set({
        "name": data["name"],
        "username": data["username"],
        "balance": 0,
        "failed_attempts": 0,
        "blocked": False
    })

    pending_ref.delete()

    await context.bot.send_message(chat_id=user_id, text="تم تفعيل حسابك ✅")
    await update.message.reply_text("تم قبول المستخدم")

# ================= REJECT =================
async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) == 0:
        await update.message.reply_text("ضع ID المستخدم بعد الأمر")
        return

    user_id = context.args[0]
    db.reference(f'users/pending/{user_id}').delete()
    await update.message.reply_text("تم رفض المستخدم")

# ================= VERIFY =================
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_ref = db.reference(f'users/approved/{user_id}')
    user = user_ref.get()

    if not user:
        await update.message.reply_text("حسابك غير مفعل.")
        return ConversationHandler.END

    if user["blocked"]:
        await update.message.reply_text("حسابك محظور ❌")
        return ConversationHandler.END

    await update.message.reply_text("ادخل مبلغ العملية:")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["amount"] = update.message.text
    await update.message.reply_text("ادخل الوقت (مثال 21:17):")
    return TIME

async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    amount = context.user_data["amount"]
    time = update.message.text

    transaction_id = f"{amount}_{time}"
    trans_ref = db.reference(f'transactions/{transaction_id}')
    trans = trans_ref.get()

    user_ref = db.reference(f'users/approved/{user_id}')
    user = user_ref.get()

    if not trans:
        failed = user["failed_attempts"] + 1
        user_ref.update({"failed_attempts": failed})

        if failed >= 3:
            user_ref.update({"blocked": True})
            await update.message.reply_text("تم حظرك بسبب 3 محاولات فاشلة ❌")
        else:
            await update.message.reply_text("عملية غير موجودة ❌")
        return ConversationHandler.END

    if trans["used"]:
        await update.message.reply_text("هذه العملية مستعملة سابقاً ❌")
        return ConversationHandler.END

    # نجاح العملية
    new_balance = user["balance"] + int(amount)
    user_ref.update({
        "balance": new_balance,
        "failed_attempts": 0
    })
    trans_ref.update({
        "used": True,
        "used_by": user_id
    })

    await update.message.reply_text(f"تم إضافة {amount} دج بنجاح ✅\nرصيدك الحالي: {new_balance}")
    return ConversationHandler.END

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^تحقق$"), verify)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_amount)],
            TIME: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_time)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(conv_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
