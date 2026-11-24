# إعداد Firebase لتطبيق بشرى 💕 (مرة واحدة، حوالي 10 دقائق)

Firebase خدمة مجانية من Google، تنقل الرسائل والقوائم بين هاتفك وهاتف بشرى.
**أنت فقط** تقوم بهذه الخطوات. بشرى لن تحتاج إلا لصق رسالة الدعوة.

> قد تختلف أسماء الأزرار قليلاً لأن Google تغيّر واجهتها أحياناً.

## 1) إنشاء المشروع
1. افتح **console.firebase.google.com** وسجّل الدخول بحساب Gmail.
2. اضغط **Create a project** (إنشاء مشروع)، وسمّه مثلاً `bouchra`.
3. أوقف **Google Analytics** (غير مطلوب)، ثم اضغط **Create project**.

## 2) تفعيل الحسابات (البريد وكلمة السر)
1. من القائمة: **Build ← Authentication ← Get started**.
2. في تبويب **Sign-in method** اختر **Email/Password**.
3. فعّل الخيار الأول (**Enable**) ثم **Save**.

## 3) إنشاء قاعدة البيانات
1. من القائمة: **Build ← Realtime Database ← Create Database**.
2. اختر الموقع **Belgium (europe-west1)**، فهو الأقرب إليكما.
3. اختر **Start in locked mode** ثم **Enable**.
4. انسخ **الرابط** الظاهر أعلى الصفحة. يشبه:
   `https://bouchra-xxxxx-default-rtdb.europe-west1.firebasedatabase.app`
   ← هذا هو **Database URL**.

## 4) قواعد الحماية (مهم جداً 🔒)
في نفس الصفحة افتح تبويب **Rules**، واحذف كل ما فيه (حتى لا يبقى أي حرف)، والصق هذا النص كما هو، ثم اضغط **Publish**.
يبدأ النص بـ `{` وينتهي بـ `}`، فلا تنسخ علامات ``` إن ظهرت:

```json
{
  "rules": {
    "users": {
      "$uid": {
        ".read": "auth != null && auth.uid === $uid",
        ".write": "auth != null && auth.uid === $uid"
      }
    },
    "codes": {
      "$code": {
        ".read": "auth != null",
        ".write": "auth != null && ((!data.exists() && newData.child('owner').val() === auth.uid && root.child('couples').child(newData.child('couple').val() + '').child('members').child(auth.uid).exists()) || (data.exists() && newData.exists() && data.child('owner').val() === auth.uid) || (data.exists() && !newData.exists() && newData.parent().parent().child('couples').child(data.child('couple').val() + '').child('members').child(auth.uid).exists()))"
      }
    },
    "couples": {
      "$cid": {
        ".read": "auth != null && data.child('members').child(auth.uid).exists()",
        ".write": "auth != null && data.child('members').child(auth.uid).exists()",
        "members": {
          "$uid": {
            ".write": "auth != null && $uid === auth.uid && newData.val() === true && (!data.parent().exists() || (!data.parent().parent().child('full').exists() && newData.parent().parent().child('full').val() === true && root.child('users').child(auth.uid).child('joinCode').exists() && root.child('codes').child(root.child('users').child(auth.uid).child('joinCode').val() + '').child('couple').val() === $cid && !newData.parent().parent().parent().parent().child('codes').child(root.child('users').child(auth.uid).child('joinCode').val() + '').exists()))"
          }
        },
        "full": {
          ".write": "auth != null && newData.val() === true && newData.parent().child('members').child(auth.uid).exists()"
        }
      }
    }
  }
}
```

هذه القواعد تجعل بياناتكما **لكما فقط**: لا يستطيع أي شخص آخر قراءتها، ولا يمكن لشخص ثالث الانضمام.

## 5) مفتاح الـ API
1. اضغط ⚙️ بجانب **Project Overview** ← **Project settings**.
2. في تبويب **General** انسخ **Web API Key** (يبدأ بـ `AIza`).
3. إذا لم يظهر المفتاح: انزل إلى **Your apps** ← اضغط أيقونة الويب **</>** ← سمّه `bouchra` ← **Register app**، ثم انسخ قيمة `apiKey` من الكود الظاهر.

هذا المفتاح ليس كلمة سر: هو عنوان مشروعك فقط، والحماية تأتي من القواعد في الخطوة 4.

## 6) في التطبيق (هاتفك أنت)
1. ثبّت النسخة 3.0 واختر **🤵 أنا الزوج**.
2. افتح **💬 الدردشة** ← الصق **Web API Key** و **Database URL** ← **حفظ ومتابعة**.
3. أنشئ حسابك (الاسم، البريد، كلمة السر).
4. اضغط **💌 إنشاء دعوة** ← **أرسل الدعوة** لبشرى على واتساب.

## 7) في هاتف بشرى
1. ثبّت التطبيق واختر **👰 أنا الزوجة (بشرى)**.
2. تنسخ رسالة الدعوة كاملة من واتساب.
3. تفتح **💬 الدردشة** ← **📥 لدي دعوة** ← تلصق ← **متابعة**.
4. تنشئ حسابها، **ويتم الربط تلقائياً** 🎉

## إذا لم تصل الإشعارات والتطبيق مغلق
- اضغط 👤 أعلى التطبيق ← **🔋 السماح بالعمل في الخلفية** ← **سماح**.
- في هواتف Samsung و Xiaomi و Huawei: الإعدادات ← التطبيقات ← Bouchra ← البطارية ← **غير مقيّد**.
- يظهر إشعار صغير دائم «💕 متصل مع ...». هذا طبيعي، فهو ما يُبقي الاتصال حياً.

## التكلفة
الخطة المجانية (Spark) تكفي شخصين بسهولة، **ولا تحتاج بطاقة بنكية**.
