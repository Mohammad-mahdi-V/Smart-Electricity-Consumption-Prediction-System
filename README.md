⚡ سامانه هوشمند پیش‌بینی مصرف برق

Smart Electricity Consumption Prediction System

<p align="center">
  <b>سگمنت‌بندی تطبیقی مبتنی بر رفتار • یادگیری ماشین • IoT • هوش انرژی</b>
</p><p align="center">
  <a href="#فارسی">🇮🇷 فارسی</a>
  &nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="#english">🇬🇧 English</a>
</p>---

<a id="فارسی"></a>

🇮🇷 فارسی

📌 معرفی پروژه

سامانه هوشمند پیش‌بینی مصرف برق یک پروژه پژوهشی و محصول‌محور است که توسط Jupiter Code توسعه داده می‌شود.

هدف پروژه ترکیب تحلیل رفتار مصرف‌کننده، سگمنت‌بندی تطبیقی، یادگیری ماشین و اندازه‌گیری واقعی برق برای ایجاد یک سامانه کم‌هزینه و بومی پیش‌بینی مصرف برق است.

اجزای اصلی پروژه:

- ⚡ پیش‌بینی مصرف برق
- 🧠 سگمنت‌بندی تطبیقی مبتنی بر رفتار
- 👥 خوشه‌بندی کاربران
- 📊 تحلیل سری زمانی
- 🤖 یادگیری ماشین
- 📡 اندازه‌گیری برق با IoT
- 🔄 سازگاری با تغییرات الگوی مصرف

«مصرف برق فقط یک سیگنال عددی نیست؛ بلکه بازتابی از رفتار مصرف‌کننده است.»

---

🎯 چشم‌انداز پروژه

ما نمی‌خواهیم این سامانه صرفاً به‌عنوان یک ایده پژوهشی باقی بماند.

هدف، حرکت از:

پژوهش
  ↓
الگوریتم
  ↓
آزمایش و بنچمارک
  ↓
نمونه اولیه
  ↓
سخت‌افزار کم‌هزینه
  ↓
محصول بومی

است.

چشم‌انداز نهایی، توسعه یک سامانه بومی، کم‌هزینه و قابل توسعه برای پایش، تحلیل و پیش‌بینی مصرف برق است.

---

🧠 سگمنت‌بندی تطبیقی مبتنی بر رفتار

مسئله اصلی

یکی از اولین ایده‌هایی که هنگام فکر کردن به سگمنت‌بندی مصرف برق به ذهن می‌رسد، کاهش واریانس درون سگمنت‌ها است.

این ایده از نظر مفهومی به روش‌هایی مانند Fisher–Jenks Natural Breaks نزدیک است.

در این رویکرد، هدف اصلی پیدا کردن نقاطی است که باعث کاهش پراکندگی درون گروه‌ها شوند.

اما این برای مسئله ما کافی نبود.

ما نمی‌خواستیم سامانه فقط بگوید:

««کجا واریانس کمتر است؟»»

بلکه می‌خواستیم بررسی کند:

««رفتار مصرف‌کننده کجا واقعاً تغییر می‌کند و آیا این تغییر پایدار و معنادار است؟»»

بنابراین سگمنت‌بندی پروژه از یک رویکرد صرفاً مبتنی بر واریانس به سمت یک رویکرد تطبیقی و رفتارمحور توسعه داده شده است.

---

🔄 فرایند سگمنت‌بندی

سامانه از داده‌های ۳۰ روز گذشته برای ساخت یک نمای رفتاری از مصرف‌کننده استفاده می‌کند.

مراحل اصلی:

1. ساخت پروفایل ساعتی مصرف
2. استفاده از میانه وزندار
3. دادن وزن بیشتر به روزهای اخیر
4. کاهش نویز
5. شناسایی تغییرات رفتاری
6. ارزیابی شدت و پایداری تغییر
7. اعمال محدودیت طول سگمنت
8. تولید چهار سگمنت پیوسته
9. به‌روزرسانی مرزها به‌صورت روزانه

پارامترهای فعلی

پارامتر| مقدار
تعداد سگمنت| ۴
حداقل طول سگمنت| ۴ ساعت
حداکثر طول سگمنت| ۷ ساعت
پنجره تاریخی| ۳۰ روز
به‌روزرسانی| روزانه

---

📐 پروفایل رفتاری

برای توجه بیشتر به رفتار اخیر، از وزن‌دهی کاهشی استفاده می‌شود:

w ∝ 0.97^age

سپس:

داده‌های تاریخی
      ↓
میانه وزندار
      ↓
پروفایل رفتاری ساعتی
      ↓
هموارسازی
      ↓
تحلیل تغییرات
      ↓
مرزهای سگمنت

این ساختار تلاش می‌کند بین دو نیاز تعادل برقرار کند:

- واکنش به تغییرات جدید رفتار
- جلوگیری از تأثیرگذاری بیش از حد یک مشاهده غیرعادی

---

📊 داده و روش ارزیابی

برای بنچمارک از داده‌های واقعی Smart Meter London استفاده شده است.

ویژگی| مقدار
Dataset| Smart Meter London
تعداد خانوار| ۱۰۰۰
بازه زمانی| دسامبر ۲۰۱۲ تا دسامبر ۲۰۱۳
نوع تقسیم| زمانی
آموزش| ۸۰٪
آزمون| ۲۰٪
افق پیش‌بینی| روز ۱، ۲ و ۳

چرا ۸۰/۲۰؟

تقسیم داده به صورت زمانی انجام شده است:

گذشته                                             آینده
────────────────────────────────────────────────────────►

|---------------------- 80% ----------------------|-- 20% --|
                       آموزش                         آزمون

۲۰٪ پایانی داده‌ها برای آزمون کنار گذاشته می‌شود.

از تقسیم تصادفی استفاده نمی‌شود، زیرا در مسئله پیش‌بینی مصرف برق باید مدل از گذشته یاد بگیرد و روی آینده‌ای که در زمان آموزش مشاهده نکرده است ارزیابی شود.

---

🤖 مدل پیش‌بینی

افق‌های مورد بررسی:

- Day 1
- Day 2
- Day 3

مدل اصلی فعلی:

Random Forest

مدل Random Forest در بنچمارک فعلی به‌عنوان مدل اصلی استفاده شده است.

با این حال، سگمنت‌بندی تطبیقی تنها یک مرحله پیش‌پردازش نیست؛ هدف آن ایجاد یک نمای رفتاری قابل استفاده در کل زنجیره پیش‌بینی است.

---

📈 نتایج بنچمارک

مقایسه Adaptive Segmentation و Jenks:

افق| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²| Naive WAPE
Day 1| 18.31%| 18.34%| 0.856| 0.857| 25.28%
Day 2| 20.28%| 20.26%| 0.782| 0.774| 25.31%
Day 3| 21.36%| 21.36%| 0.605| 0.692| 25.42%

نتایج نشان می‌دهند که Adaptive و Jenks در معیار WAPE عملکرد بسیار نزدیکی در افق‌های بررسی‌شده دارند.

بنابراین هدف پروژه ادعای برتری مطلق یک روش در همه معیارها نیست.

تمرکز اصلی بر بررسی این موضوع است که آیا نمایش تطبیقی و رفتارمحور می‌تواند ضمن حفظ عملکرد رقابتی، ساختار مصرف کاربران را بهتر مدل کند.

---

👥 خوشه‌بندی کاربران

در کنار سگمنت‌بندی روزانه، رفتار کاربران نیز بررسی شده است.

نتایج فعلی:

- ۹۴۸ دستگاه خوشه‌بندی‌شده
- ۵۲ دستگاه پرت
- ۲ خوشه اصلی

این بخش می‌تواند در آینده برای موارد زیر استفاده شود:

- مدل‌های اختصاصی کاربران
- پیش‌بینی شخصی‌سازی‌شده
- پروفایل رفتاری
- انتخاب مدل مناسب برای هر گروه

---

🔬 اثر خوشه‌بندی بر مدل‌ها

اثر خوشه‌بندی به الگوریتم پیش‌بینی وابسته است.

مدل| Day 1| Day 2| Day 3
Ridge| +79.8%| +66.0%| +31.2%
Random Forest| −1.1%| −1.2%| −0.8%

این نتایج نشان می‌دهند که یک روش پیش‌پردازش یا تقسیم‌بندی واحد الزاماً برای تمام مدل‌های پیش‌بینی اثر یکسانی ندارد.

---

🏗️ معماری سامانه

"معماری سامانه" (docs/architecture.png)

                 ┌──────────────────────┐
                 │     داده مصرف برق    │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │    پیش‌پردازش داده   │
                 └──────────┬───────────┘
                            │
                            ▼
              ┌────────────────────────────┐
              │ سگمنت‌بندی تطبیقی مبتنی   │
              │          بر رفتار          │
              └────────────┬───────────────┘
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
        ┌────────────────┐   ┌────────────────┐
        │ خوشه‌بندی کاربر│   │ استخراج ویژگی │
        └───────┬────────┘   └───────┬────────┘
                │                    │
                └──────────┬─────────┘
                           ▼
                 ┌──────────────────────┐
                 │    Random Forest     │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │    پیش‌بینی مصرف     │
                 └──────────────────────┘

---

📡 نمونه سخت‌افزاری کم‌هزینه

پروژه در کنار بخش نرم‌افزاری، یک نمونه اولیه سخت‌افزاری نیز دارد.

اجزای اصلی

- ESP32
- CT Clamp
- B101ZMPT
- Wi-Fi

پارامترهای مورد اندازه‌گیری:

- ولتاژ RMS
- جریان RMS
- توان واقعی
- توان ظاهری
- ضریب توان

---

⚡ اندازه‌گیری ولتاژ

در نسخه اولیه، ولتاژ تقریباً ۲۳۰ ولت فرض می‌شد.

در نسخه جدید، ولتاژ و جریان به‌صورت همزمان اندازه‌گیری می‌شوند تا محاسبات به شرایط واقعی شبکه نزدیک‌تر شوند.

Vrms
Irms
Real Power
Apparent Power
Power Factor

---

📡 مسیر داده سخت‌افزار

              شبکه برق
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
    CT Clamp           B101ZMPT
     جریان               ولتاژ
        │                   │
        └─────────┬─────────┘
                  ▼
                ESP32
                  │
                  ▼
            پردازش محلی
                  │
                  ▼
                Wi-Fi
                  │
                  ▼
               Server
                  │
                  ▼
        AI / Forecasting

نمونه پیام:

{
  "current_A": 2.145,
  "voltage_V": 228.4,
  "power_W": 478.2,
  "apparent_power_VA": 490.1,
  "power_factor": 0.976
}

---

🎯 پژوهش → نمونه اولیه → محصول

       پژوهش
          │
          ▼
 الگوریتم تطبیقی
          │
          ▼
       بنچمارک
          │
          ▼
     نمونه اولیه
          │
          ▼
  سخت‌افزار کم‌هزینه
          │
          ▼
        محصول

هدف نهایی، حرکت از یک ایده پژوهشی به سمت یک محصول بومی کم‌هزینه و قابل استفاده است.

---

🛣️ نقشه راه

پیش‌بینی

- [ ] بهبود Day 1
- [ ] توسعه مدل‌های تخصصی Day 2 و Day 3
- [ ] بررسی الگوریتم‌های پیش‌بینی بیشتر
- [ ] مقایسه Direct و Horizon-Specific Forecasting

سگمنت‌بندی

- [ ] بهبود تشخیص تغییرات رفتاری
- [ ] بررسی معیارهای پایداری
- [ ] بررسی رفتار فصلی
- [ ] بررسی تعداد سگمنت‌های تطبیقی

خوشه‌بندی

- [ ] بررسی روش‌های بیشتر
- [ ] تشخیص بهتر کاربران پرنوسان
- [ ] توسعه مدل‌های تخصصی گروه‌ها

سخت‌افزار

- [ ] بهبود کالیبراسیون
- [ ] مقایسه با ابزارهای مرجع
- [ ] افزایش قابلیت اطمینان
- [ ] طراحی بدنه
- [ ] کاهش هزینه ساخت

محصول

- [ ] اتصال سخت‌افزار و مدل پیش‌بینی
- [ ] توسعه داشبورد
- [ ] توسعه زیرساخت تحلیل محلی
- [ ] تست میدانی
- [ ] توسعه نسخه قابل عرضه

---

⚠️ محدودیت‌های فعلی

پروژه همچنان در حال توسعه است.

محدودیت‌های فعلی:

- رفتار کاربران مختلف است.
- کاربران بسیار پرنوسان چالش بیشتری ایجاد می‌کنند.
- پیش‌بینی Day 2 و Day 3 نیازمند توسعه بیشتر است.
- اثر خوشه‌بندی به مدل پیش‌بینی وابسته است.
- کالیبراسیون سخت‌افزار نیازمند اعتبارسنجی دقیق است.
- دیتاست مورد استفاده نماینده تمام الگوهای مصرف ممکن نیست.

این موارد بخشی از مسیر تحقیق و توسعه پروژه هستند.

---

🌱 فلسفه پروژه

«فقط چیزی را که اندازه‌گیری آن آسان است بهینه نکن؛ چیزی را مدل کن که واقعاً اهمیت دارد.»

واریانس یک معیار مهم است، اما واریانس به‌تنهایی لزوماً رفتار مصرف‌کننده را توصیف نمی‌کند.

به همین دلیل پروژه ترکیبی از:

آمار + رفتار + سازگاری + یادگیری ماشین + اندازه‌گیری واقعی

را دنبال می‌کند.

---

📚 Dataset

داده مورد استفاده:

Smart Meter Energy Consumption Data in London Households

است.

استفاده از داده تابع شرایط و مجوز منبع اصلی داده است.

---

📺 نمایش پروژه

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

---

📜 استناد

در صورت استفاده قابل‌توجه از پروژه در مقاله، پژوهش، ارائه، مسابقه، پروژه دانشگاهی یا پروژه مشتق‌شده، لطفاً به پروژه استناد دهید:

«Smart Electricity Consumption Prediction System
Jupiter Code / Mohammad Mahdi Vafri»

---

⚖️ Copyright / License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

این پروژه تحت:

Jupiter Code Non-Commercial License v1.1

منتشر شده است.

استفاده شخصی، آموزشی، دانشگاهی، علمی، پژوهشی و سایر استفاده‌های غیرتجاری، مطابق شرایط مجوز، مجاز است.

استفاده تجاری

استفاده تجاری نیازمند اجازه کتبی صاحب حق است، مگر اینکه تحت مجوز تجاری جداگانه مجاز شده باشد.

این موارد شامل، اما محدود به موارد زیر نیست:

- محصولات تجاری
- خدمات پولی
- SaaS تجاری
- توزیع تجاری
- صدور مجوز تجاری
- استفاده در سامانه‌های تجاری

کتابخانه‌ها، دیتاست‌ها، مدل‌های ازپیش‌آموزش‌دیده و سایر اجزای شخص ثالث تابع مجوزهای خود هستند.

متن کامل مجوز:

""LICENSE.md"" (LICENSE.md)

---

👨‍💻توسعه دهنده

Jupiter Code Team

© 2026 Jupiter Code / Mohammad Mahdi Vafri

---

<a id="english"></a>

🇬🇧 English

📌 Overview

Smart Electricity Consumption Prediction System is a research-to-product project developed by Jupiter Code.

The project combines consumer behavior analysis, adaptive segmentation, machine learning, and real electricity measurement to develop a low-cost and locally developed electricity forecasting system.

Core components:

- ⚡ Electricity consumption forecasting
- 🧠 Behavior-aware adaptive segmentation
- 👥 User clustering
- 📊 Time-series analysis
- 🤖 Machine learning
- 📡 IoT-based electricity measurement
- 🔄 Adaptation to changing consumption patterns

«Electricity consumption is not merely a numerical signal; it is a reflection of consumer behavior.»

---

🎯 Project Vision

We do not want this system to remain only a research idea.

The goal is to move from:

Research
   ↓
Algorithm
   ↓
Benchmark
   ↓
Prototype
   ↓
Low-Cost Hardware
   ↓
Local Product

toward a low-cost, locally developed and scalable electricity monitoring and forecasting product.

---

🧠 Behavior-Aware Adaptive Segmentation

The Core Problem

One of the first ideas that naturally comes to mind when segmenting electricity consumption is to reduce variance within segments.

Conceptually, this is related to methods such as Fisher–Jenks Natural Breaks.

Such methods are useful for statistical partitioning and reducing within-segment dispersion.

However, that was not sufficient for our objective.

We did not want the system to answer only:

«"Where is the variance lower?"»

We wanted it to investigate:

«"Where does consumer behavior actually change, and is that change meaningful and persistent?"»

Therefore, the segmentation approach was developed from a purely variance-oriented approach toward an adaptive, behavior-aware approach.

---

🔄 Adaptive Segmentation Pipeline

The system uses the previous 30 days to construct a behavioral representation of recent consumption.

Main steps:

1. Build an hourly consumption profile.
2. Apply a weighted median.
3. Give more weight to recent observations.
4. Reduce short-term noise.
5. Detect behavioral changes.
6. Evaluate change strength and persistence.
7. Apply segment-length constraints.
8. Generate four contiguous segments.
9. Update boundaries daily.

Current parameters

Parameter| Value
Number of segments| 4
Minimum segment length| 4 hours
Maximum segment length| 7 hours
Historical window| 30 days
Update frequency| Daily

---

📐 Behavioral Profile

Recent observations receive higher importance using a decay-based weighting scheme:

w ∝ 0.97^age

The process is:

Historical Data
      ↓
Weighted Median
      ↓
Hourly Behavioral Profile
      ↓
Smoothing
      ↓
Change Analysis
      ↓
Segment Boundaries

This is intended to balance:

- responsiveness to recent behavioral changes
- robustness against isolated abnormal observations

---

📊 Dataset & Evaluation

The benchmark uses real-world Smart Meter London electricity consumption data.

Property| Value
Dataset| Smart Meter London
Households| 1,000
Period| December 2012 – December 2013
Split| Temporal
Training| 80%
Testing| 20%
Forecast Horizons| Day 1, Day 2, Day 3

Why 80/20?

The split is chronological:

PAST                                                   FUTURE
────────────────────────────────────────────────────────────►

|---------------------- 80% ----------------------|-- 20% --|
                     TRAINING                         TEST

The final 20% of the timeline is reserved for testing.

A random split is not used because a forecasting model should learn from past observations and be evaluated on future observations that were not available during training.

---

🤖 Forecasting

The evaluated forecasting horizons are:

- Day 1
- Day 2
- Day 3

Current primary model:

Random Forest

Random Forest is used as the primary forecasting model in the current benchmark.

The adaptive segmentation component is intended to provide an explicit behavioral representation within the forecasting pipeline.

---

📈 Benchmark Results

Comparison between Adaptive Segmentation and Jenks:

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²| Naive WAPE
Day 1| 18.31%| 18.34%| 0.856| 0.857| 25.28%
Day 2| 20.28%| 20.26%| 0.782| 0.774| 25.31%
Day 3| 21.36%| 21.36%| 0.605| 0.692| 25.42%

The results show that Adaptive and Jenks segmentation produce very similar WAPE values across the evaluated horizons.

The goal is therefore not to claim universal superiority across every metric.

Instead, the project investigates whether a behavior-aware adaptive representation can remain competitive while providing a more dynamic representation of user consumption behavior.

---

👥 User Clustering

User behavior is also analyzed through clustering.

Current reported results:

- 948 clustered devices
- 52 outlier devices
- 2 main behavioral clusters

This component can support future:

- User-specific models
- Personalized forecasting
- Behavioral profiling
- Model selection

---

🔬 Clustering & Forecasting

The effect of clustering depends on the forecasting algorithm.

Reported WAPE changes:

Model| Day 1| Day 2| Day 3
Ridge| +79.8%| +66.0%| +31.2%
Random Forest| −1.1%| −1.2%| −0.8%

These results show that clustering does not have the same effect across forecasting algorithms.

---

🏗️ System Architecture

"System Architecture" (docs/architecture.png)

                 ┌──────────────────────┐
                 │ Electricity Data     │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ Data Preprocessing   │
                 └──────────┬───────────┘
                            │
                            ▼
              ┌────────────────────────────┐
              │ Behavior-Aware Adaptive    │
              │ Segmentation               │
              └────────────┬───────────────┘
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
        ┌────────────────┐   ┌────────────────┐
        │ User Clustering│   │ Feature Engine │
        └───────┬────────┘   └───────┬────────┘
                │                    │
                └──────────┬─────────┘
                           ▼
                 ┌──────────────────────┐
                 │    Random Forest     │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ Consumption Forecast │
                 └──────────────────────┘

---

📡 Low-Cost Hardware Prototype

The project also includes a hardware prototype for electricity measurement.

Main components

- ESP32
- CT Clamp
- B101ZMPT
- Wi-Fi

Measured parameters:

- RMS voltage
- RMS current
- Real power
- Apparent power
- Power factor

---

⚡ Voltage Measurement

The initial prototype approximately assumed a fixed 230 V supply.

The updated prototype measures voltage and current simultaneously, allowing the measurement layer to better represent real grid conditions.

Vrms
Irms
Real Power
Apparent Power
Power Factor

---

📡 Hardware Data Flow

              Electricity Grid
                     │
           ┌─────────┴─────────┐
           ▼                   ▼
       CT Clamp           B101ZMPT
        Current             Voltage
           │                   │
           └─────────┬─────────┘
                     ▼
                   ESP32
                     │
                     ▼
              Local Processing
                     │
                     ▼
                   Wi-Fi
                     │
                     ▼
                  Server
                     │
                     ▼
             AI / Forecasting

Example message:

{
  "current_A": 2.145,
  "voltage_V": 228.4,
  "power_W": 478.2,
  "apparent_power_VA": 490.1,
  "power_factor": 0.976
}

---

🎯 Research → Prototype → Product

        RESEARCH
           │
           ▼
   Adaptive Algorithm
           │
           ▼
        BENCHMARK
           │
           ▼
        PROTOTYPE
           │
           ▼
     LOW-COST HARDWARE
           │
           ▼
          PRODUCT

The long-term objective is to transform the research concept into a low-cost, locally developed and deployable energy-intelligence product.

---

🛣️ Roadmap

Forecasting

- [ ] Improve Day-1 forecasting
- [ ] Develop specialized Day-2 and Day-3 models
- [ ] Evaluate additional forecasting algorithms
- [ ] Compare direct and horizon-specific forecasting

Adaptive Segmentation

- [ ] Improve behavioral change detection
- [ ] Investigate stronger persistence measures
- [ ] Study seasonal behavior
- [ ] Investigate adaptive segment counts

Clustering

- [ ] Evaluate additional clustering methods
- [ ] Improve volatile-user detection
- [ ] Develop specialized models for behavioral groups

Hardware

- [ ] Improve calibration
- [ ] Validate against reference instruments
- [ ] Improve reliability
- [ ] Develop a practical enclosure
- [ ] Reduce production cost

Product

- [ ] Integrate hardware and forecasting
- [ ] Develop monitoring dashboard
- [ ] Build local analytics infrastructure
- [ ] Conduct field testing
- [ ] Develop a deployable product version

---

⚠️ Current Limitations

The project is still under active development.

Current limitations include:

- Consumption behavior varies substantially between users.
- Highly volatile users remain challenging.
- Day-2 and Day-3 forecasting require further development.
- The effect of clustering depends on the forecasting model.
- Hardware calibration requires careful validation.
- The benchmark dataset does not represent every possible household consumption pattern.

These limitations are part of the ongoing research and development process.

---

🌱 Project Philosophy

«Do not optimize only what is easy to measure; model what actually matters.»

Variance is useful, but variance alone does not necessarily describe consumer behavior.

Therefore, the project combines:

Statistics + Behavior + Adaptation + Machine Learning + Real Measurement

to develop an electricity-intelligence system.

---

📚 Dataset

The benchmark uses:

Smart Meter Energy Consumption Data in London Households

Use of the dataset remains subject to the terms and license of its original source.

---

📺 Demonstration

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

---

📜 Citation

If substantial parts of this project are used in research, publications, presentations, competitions, academic projects, or derivative projects, please provide attribution:

«Smart Electricity Consumption Prediction System
Jupiter Code / Mohammad Mahdi Vafri»

---

⚖️ Copyright / License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

This project is released under:

Jupiter Code Non-Commercial License v1.1

Personal, educational, academic, scientific, research, and other permitted non-commercial uses are allowed subject to the terms of the license.

Commercial Use

Commercial use requires prior written permission from the Copyright Holder, unless separately authorized under a commercial license.

This includes, but is not limited to:

- Commercial products
- Paid services
- Commercial SaaS deployments
- Commercial redistribution
- Commercial licensing
- Integration into commercial systems

Third-party libraries, datasets, pretrained models, APIs, and other external components remain subject to their respective licenses.

Full license terms:

""LICENSE.md"" (LICENSE.md)

---

👨‍💻 Author


Jupiter Code Team

Smart Electricity Consumption Prediction System

© 2026 Jupiter Code 

---

<p align="center">
  <b>Research → Prototype → Product</b>
  <br>
  Adaptive Intelligence for Electricity Consumption
</p>