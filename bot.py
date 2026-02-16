import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import firebase_admin
from firebase_admin import credentials, db

# ======================== ضع بياناتك هنا ========================
TOKEN = "8572697288:AAHPnY9hu7ktLrmsy1J_i3KWY5OoolOcxvY"  # TOKEN بوتك
ADMIN_ID = 872300006                                         # ID الأدمن
FIREBASE_URL = "https://speed-recive-system-default-rtdb.europe-west1.firebasedatabase.app/"  # رابط Firebase
cred = credentials.Certificate("serviceAccountKey.json")      # ملف الخدمة من Firebase
# =================================================================

# تهيئة Firebase
firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_URL
})

logging.basicConfig(level=logging.INFO)

AMOUNT, TIME = range(2)

# ================= START =================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)

    approved_ref = db.reference(f'users/approved/{user_id}')
    pending_ref = db.reference(f'users/pending/{user_id}')

    if approved_ref.get():
        update.message.reply_text("مرحباً بك ✅\nاكتب تحقق لبدء عملية التحقق.")
        return ConversationHandler.END

    if pending_ref.get():
        update.message.reply_text("طلبك قيد المراجعة ⏳")
        return ConversationHandler.END

    pending_ref.set({
        "name": user.first_name,
        "username": user.username,
    })

    context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"طلب تسجيل جديد\n\nID: {user_id}\nالاسم: {user.first_name}\n\n/approve {user_id}\n/reject {user_id}"
    )

    update.message.reply_text("تم إرسال طلب التسجيل ✅")
    return ConversationHandler.END

# ================= APPROVE =================
def approve(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) == 0:
        update.message.reply_text("ضع ID المستخدم بعد الأمر")
        return

    user_id = context.args[0]

    pending_ref = db.reference(f'users/pending/{user_id}')
    data = pending_ref.get()

    if not data:
        update.message.reply_text("لا يوجد طلب بهذا ID")
        return

    db.reference(f'users/approved/{user_id}').set({
        "name": data["name"],
        "username": data["username"],
        "balance": 0,
        "failed_attempts": 0,
        "blocked": False
    })

    pending_ref.delete()

    context.bot.send_message(chat_id=user_id, text="تم تفعيل حسابك ✅")
    update.message.reply_text("تم قبول المستخدم")

# ================= REJECT =================
def reject(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) == 0:
        update.message.reply_text("ضع ID المستخدم بعد الأمر")
        return

    user_id = context.args[0]
    db.reference(f'users/pending/{user_id}').delete()
    update.message.reply_text("تم رفض المستخدم")

# ================= VERIFY =================
def verify(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    user_ref = db.reference(f'users/approved/{user_id}')
    user = user_ref.get()

    if not user:
        update.message.reply_text("حسابك غير مفعل.")
        return ConversationHandler.END

    if user["blocked"]:
        update.message.reply_text("حسابك محظور ❌")
        return ConversationHandler.END

    update.message.reply_text("ادخل مبلغ العملية:")
    return AMOUNT

def get_amount(update: Update, context: CallbackContext):
    context.user_data["amount"] = update.message.text
    update.message.reply_text("ادخل الوقت (مثال 21:17):")
    return TIME

def get_time(update: Update, context: CallbackContext):
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
            update.message.reply_text("تم حظرك بسبب 3 محاولات فاشلة ❌")
        else:
            update.message.reply_text("عملية غير موجودة ❌")

        return ConversationHandler.END

    if trans["used"]:
        update.message.reply_text("هذه العملية مستعملة سابقاً ❌")
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

    update.message.reply_text(f"تم إضافة {amount} دج بنجاح ✅\nرصيدك الحالي: {new_balance}")
    return ConversationHandler.END

# ================= MAIN =================
def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex("^تحقق$"), verify)],
        states={
            AMOUNT: [MessageHandler(Filters.text & ~Filters.command, get_amount)],
            TIME: [MessageHandler(Filters.text & ~Filters.command, get_time)],
        },
        fallbacks=[]
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("approve", approve))
    dp.add_handler(CommandHandler("reject", reject))
    dp.add_handler(conv)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
