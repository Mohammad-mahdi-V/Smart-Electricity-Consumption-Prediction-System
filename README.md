<div align="center">⚡ سامانه هوشمند پیش‌بینی مصرف برق

Smart Electricity Consumption Prediction System

سگمنت‌بندی تطبیقی مبتنی بر رفتار • یادگیری ماشین • IoT • هوش انرژی

<br><a href="#فارسی">🇮🇷 فارسی</a>
  •  
<a href="#english">🇬🇧 English</a>

</div>---

<a id="فارسی"></a>

🇮🇷 فارسی

📌 معرفی

سامانه هوشمند پیش‌بینی مصرف برق یک پروژه پژوهشی و محصول‌محور است که توسط Jupiter Code توسعه داده می‌شود.

هدف پروژه، ترکیب تحلیل رفتار مصرف‌کننده، سگمنت‌بندی تطبیقی، یادگیری ماشین و اندازه‌گیری واقعی برق برای توسعه یک سامانه کم‌هزینه، بومی و قابل استفاده در محیط واقعی است.

اجزای اصلی

- ⚡ پیش‌بینی مصرف برق
- 🧠 سگمنت‌بندی تطبیقی مبتنی بر رفتار
- 👥 خوشه‌بندی کاربران
- 📊 تحلیل سری زمانی
- 🤖 یادگیری ماشین
- 📡 اندازه‌گیری واقعی برق با IoT
- 🔄 سازگاری با تغییرات الگوی مصرف

«مصرف برق فقط یک سیگنال عددی نیست؛ بلکه بازتابی از رفتار مصرف‌کننده است.»

---

🎯 هدف پروژه

ما نمی‌خواهیم این سامانه صرفاً به‌عنوان یک ایده پژوهشی باقی بماند.

هدف، توسعه یک سامانه واقعی، کم‌هزینه و بومی برای اندازه‌گیری، تحلیل و پیش‌بینی مصرف برق است.

پروژه هم‌زمان روی الگوریتم، پیش‌بینی، اندازه‌گیری و یکپارچه‌سازی کار می‌کند تا فاصله میان پژوهش و نمونه قابل استفاده کوتاه باشد.

مسیر توسعه

پژوهش و الگوریتم
       ↓
اعتبارسنجی روی داده واقعی
       ↓
نمونه یکپارچه
       ↓
محصول کم‌هزینه

این مسیر به معنای شروع محصول از صفر نیست؛ بخش‌های اصلی سامانه از جمله الگوریتم سگمنت‌بندی، مدل پیش‌بینی و نمونه اندازه‌گیری در حال توسعه و یکپارچه‌سازی هستند.

---

🧠 سگمنت‌بندی تطبیقی مبتنی بر رفتار

مسئله چیست؟

یکی از اولین ایده‌هایی که در سگمنت‌بندی مصرف برق به ذهن می‌رسد، کاهش واریانس درون سگمنت‌ها است.

این ایده از نظر مفهومی به روش‌هایی مانند Fisher–Jenks Natural Breaks نزدیک است.

در روش Jenks، روز ۲۴ ساعته به چهار بخش پیوسته تقسیم می‌شود تا پراکندگی درون بخش‌ها کمینه شود و مرزها پس از محاسبه ثابت باقی می‌مانند.

اما این برای مسئله ما کافی نبود.

ما نمی‌خواستیم سامانه فقط بگوید:

«کجا واریانس کمتر است؟»

بلکه می‌خواستیم بررسی کند:

«رفتار مصرف‌کننده کجا واقعاً تغییر می‌کند و آیا این تغییر پایدار و تکرارشونده است؟»

به همین دلیل، روش پروژه از یک رویکرد صرفاً مبتنی بر واریانس به سمت یک رویکرد تطبیقی و رفتارمحور توسعه داده شده است.

---

🔄 ایده روش پیشنهادی

برای هر روز، فقط از ۳۰ روز قبل استفاده می‌شود.

فرایند کلی:

داده ۳۰ روز گذشته
        ↓
Weighted Median
        ↓
پروفایل رفتاری ساعتی
        ↓
Smoothing
        ↓
تحلیل تغییرات
        ↓
ارزیابی پایداری تغییر
        ↓
اعمال محدودیت سگمنت
        ↓
۴ سگمنت پیوسته

پارامترهای فعلی

پارامتر| مقدار
تعداد سگمنت| ۴
حداقل طول| ۴ ساعت
حداکثر طول| ۷ ساعت
پنجره تاریخی| ۳۰ روز
به‌روزرسانی مرزها| روزانه

مرزها هر روز دوباره محاسبه می‌شوند و از رفتار اخیر کاربر تأثیر می‌گیرند.

---

📐 وزن‌دهی به رفتار اخیر

برای اینکه رفتار روزهای اخیر اهمیت بیشتری داشته باشد:

w ∝ 0.97^age

یعنی با افزایش فاصله زمانی، وزن مشاهده کاهش پیدا می‌کند.

هدف این طراحی ایجاد تعادل میان دو عامل است:

- واکنش سریع‌تر به تغییر رفتار
- مقاومت در برابر نویز و مشاهده‌های غیرعادی

---

📊 داده و ارزیابی

Benchmark فعلی با داده واقعی Smart Meter London انجام شده است.

ویژگی| مقدار
Dataset| Smart Meter London
خانوار| ۱۰۰۰
بازه| دسامبر ۲۰۱۲ تا دسامبر ۲۰۱۳
تقسیم| زمانی
آموزش| ۸۰٪
آزمون| ۲۰٪
افق‌ها| Day 1 / Day 2 / Day 3
استراتژی| Direct Forecasting

۲۰٪ پایانی داده‌ها برای آزمون استفاده شده‌اند.

چرا تقسیم ۸۰/۲۰؟

در سری‌های زمانی، ترتیب زمانی داده اهمیت دارد.

گذشته                                      آینده

|------------- 80% -------------|---- 20% ---->
          Training                    Test

بنابراین داده‌ها به‌صورت تصادفی Shuffle نشده‌اند.

مدل از گذشته یاد می‌گیرد و روی بخش آینده‌ای که در آموزش ندیده است ارزیابی می‌شود.

---

🤖 مدل پیش‌بینی

مدل اصلی فعلی:

Random Forest

در Benchmark فعلی، یک Random Forest سراسری با روش‌های مختلف سگمنت‌بندی مقایسه شده است.

افق‌های بررسی‌شده:

- Day 1
- Day 2
- Day 3

بر اساس نتایج فعلی، Random Forest به‌عنوان مدل اصلی نگه داشته شده است.

---

📈 نتایج Benchmark

Adaptive Segmentation در برابر Jenks

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²| Naive WAPE
Day 1| 18.31%| 18.34%| 0.856| 0.857| 25.28%
Day 2| 20.28%| 20.26%| 0.782| 0.774| 25.31%
Day 3| 21.36%| 21.36%| 0.605| 0.692| 25.42%

در Day 1 و Day 2، WAPE دو روش بسیار نزدیک است.

در Day 3، تفاوت بیشتری در R² مشاهده می‌شود. مستندات پروژه همچنین پایداری متفاوت دو روش را در دستگاه‌های سخت‌تر بررسی کرده‌اند.

دستگاه‌های سخت‌تر

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²
Day 1| 24.64%| 23.73%| 0.837| 0.870
Day 2| 32.08%| 31.16%| 0.482| 0.418
Day 3| 37.21%| 33.95%| 0.824| -0.023

این بخش مربوط به دستگاه‌های پرت یا دارای سابقه کوتاه‌تر است.

«هدف این Benchmark ادعای برتری مطلق یک روش در تمام معیارها نیست؛ بلکه بررسی عملکرد و پایداری سگمنت‌بندی تطبیقی در شرایط مختلف است.»

---

👥 خوشه‌بندی کاربران

در کنار سگمنت‌بندی روزانه، رفتار کاربران نیز با روش‌های خوشه‌بندی بررسی شده است.

نتیجه فعلی:

- ۹۴۸ دستگاه خوشه‌بندی‌شده
- ۵۲ دستگاه پرت
- ۲ خوشه اصلی

دو الگوی اصلی گزارش شده‌اند:

- 🟢 خوشه منظم: ۶۲۶ دستگاه
- 🟠 خوشه پرنوسان: ۳۲۱ دستگاه

WAPE تقریبی خوشه منظم حدود ۱۵ تا ۱۷ درصد و خوشه پرنوسان حدود ۲۴ تا ۲۸ درصد گزارش شده است.

---

🔬 اثر خوشه‌بندی روی مدل

اثر خوشه‌بندی به مدل پیش‌بینی وابسته است.

مدل| Day 1| Day 2| Day 3
Ridge| +79.8%| +66.0%| +31.2%
Random Forest| -1.1%| -1.2%| -0.8%

این نتایج نشان می‌دهند که خوشه‌بندی الزاماً برای تمام مدل‌ها اثر یکسانی ندارد.

در نتیجه، خوشه‌بندی به‌عنوان یک ابزار تحلیلی و قابل توسعه در معماری پروژه باقی می‌ماند.

---

🏗️ معماری سامانه

معماری اصلی پروژه به شکل زیر است:

                 ┌─────────────────┐
                 │  Electricity    │
                 │      Data       │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Preprocessing   │
                 └────────┬────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Adaptive Segmentation │
              └───────────┬───────────┘
                          │
                 ┌────────┴────────┐
                 │                 │
                 ▼                 ▼
          User Clustering    Feature Engineering
                 │                 │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │  Random Forest  │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Consumption     │
                 │   Forecast      │
                 └─────────────────┘

---

📡 نمونه سخت‌افزاری کم‌هزینه

پروژه در کنار بخش نرم‌افزاری، نمونه اولیه اندازه‌گیری واقعی برق را نیز توسعه داده است.

اجزای اصلی

- ESP32
- CT Clamp
- B101ZMPT
- Wi-Fi

در نسخه جدید، ولتاژ و جریان به‌صورت همزمان نمونه‌برداری می‌شوند. در نتیجه امکان محاسبه موارد زیر فراهم شده است:

- RMS Voltage
- RMS Current
- Real Power
- Apparent Power
- Power Factor

افزودن B101ZMPT برای رفع فرض ثابت بودن ولتاژ و نزدیک‌تر شدن اندازه‌گیری به شرایط واقعی شبکه انجام شده است.

---

⚡ مسیر اندازه‌گیری

Electricity Grid
       │
       ├──────────────┐
       ▼              ▼
   CT Clamp       B101ZMPT
    Current         Voltage
       │              │
       └──────┬───────┘
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

ولتاژ، جریان، توان واقعی، توان ظاهری و ضریب توان محاسبه می‌شوند. داده‌ها در نمونه فعلی هر ۱۰ ثانیه به سرور ارسال می‌شوند.

نمونه داده

{
  "current_A": 2.145,
  "voltage_V": 228.4,
  "power_W": 478.2,
  "apparent_power_VA": 490.1,
  "power_factor": 0.976
}

---

🔧 تغییر مهم سخت‌افزار

در نسخه اولیه، ولتاژ حدود ۲۳۰ ولت فرض می‌شد.

در نسخه جدید:

- سنسور ولتاژ B101ZMPT اضافه شده است.
- ولتاژ واقعی اندازه‌گیری می‌شود.
- ولتاژ و جریان همزمان نمونه‌برداری می‌شوند.
- توان واقعی محاسبه می‌شود.
- توان ظاهری محاسبه می‌شود.
- ضریب توان محاسبه می‌شود.

این تغییر در پاسخ به مسئله ثابت فرض کردن ولتاژ انجام شده است.

---

🎯 از پژوهش تا محصول

پروژه با رویکرد Research-to-Product توسعه داده می‌شود.

Research
   ↓
Benchmark
   ↓
Integrated Prototype
   ↓
Low-Cost Product

تمرکز اصلی اکنون روی تکمیل و یکپارچه‌سازی اجزای موجود است، نه ایجاد یک مسیر طولانی و جداگانه برای رسیدن به محصول.

هدف نهایی

«توسعه یک سامانه هوشمند، کم‌هزینه و بومی برای اندازه‌گیری، تحلیل و پیش‌بینی مصرف برق.»

---

🛣️ نقشه راه

⚡ پیش‌بینی

- [ ] بهبود دقت Day 1
- [ ] توسعه مدل اختصاصی Day 2
- [ ] توسعه مدل اختصاصی Day 3
- [ ] مقایسه الگوریتم‌های پیش‌بینی
- [ ] بررسی Horizon-Specific Forecasting

🧠 سگمنت‌بندی

- [ ] بهبود تشخیص تغییر رفتار
- [ ] بهبود معیار پایداری
- [ ] بررسی رفتار فصلی
- [ ] بررسی تعداد سگمنت‌های تطبیقی

👥 خوشه‌بندی

- [ ] مقایسه روش‌های بیشتر
- [ ] تشخیص بهتر کاربران پرنوسان
- [ ] توسعه مدل‌های اختصاصی گروه‌ها

📡 سخت‌افزار

- [ ] بهبود کالیبراسیون
- [ ] مقایسه با ابزار مرجع
- [ ] افزایش قابلیت اطمینان
- [ ] بهبود طراحی فیزیکی
- [ ] کاهش هزینه ساخت

🚀 محصول

- [ ] تکمیل اتصال سخت‌افزار و مدل
- [ ] توسعه داشبورد
- [ ] تکمیل Backend
- [ ] تست میدانی
- [ ] آماده‌سازی نسخه قابل استفاده

---

⚠️ محدودیت‌های فعلی

پروژه همچنان در حال توسعه است.

محدودیت‌های فعلی:

- رفتار مصرف کاربران متفاوت است.
- کاربران پرنوسان دشوارتر پیش‌بینی می‌شوند.
- Day 2 و Day 3 نیازمند توسعه بیشتر هستند.
- اثر خوشه‌بندی به مدل پیش‌بینی وابسته است.
- سخت‌افزار نیازمند کالیبراسیون و اعتبارسنجی دقیق است.
- Dataset مورد استفاده نماینده تمام الگوهای مصرف ممکن نیست.

این موارد بخشی از مسیر تحقیق و توسعه فعلی پروژه هستند.

---

🌱 فلسفه پروژه

««فقط چیزی را که اندازه‌گیری آن آسان است بهینه نکن؛ چیزی را مدل کن که واقعاً اهمیت دارد.»»

ایده اصلی پروژه این است که واریانس به‌تنهایی برای توصیف رفتار مصرف‌کننده کافی نیست.

بنابراین پروژه ترکیبی از:

Statistics + Behavior + Adaptation + Machine Learning + Real Measurement

را دنبال می‌کند.

---

📚 Dataset

داده مورد استفاده:

Smart Meter Energy Consumption Data in London Households

منبع داده:

https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d

استفاده از Dataset تابع شرایط و مجوز منبع اصلی داده است.

---

📺 نمایش پروژه

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

در این کانال، ویدیوی جدید پروژه و مقایسه نمودارهای نتایج نیز منتشر شده است.

---

📜 Citation

در صورت استفاده قابل‌توجه از پروژه در مقاله، پژوهش، ارائه، مسابقه، پروژه دانشگاهی یا پروژه مشتق‌شده، لطفاً به پروژه استناد دهید:

«Smart Electricity Consumption Prediction System
Jupiter Code / Mohammad Mahdi Vafri»

---

⚖️ Copyright & License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

این پروژه تحت مجوز:

Jupiter Code Non-Commercial License v1.1

منتشر شده است.

استفاده‌های مجاز

- استفاده شخصی
- استفاده آموزشی
- استفاده دانشگاهی
- استفاده علمی
- استفاده پژوهشی
- سایر استفاده‌های غیرتجاری مجاز طبق شرایط License

استفاده تجاری

استفاده تجاری نیازمند اجازه کتبی صاحب حق است، مگر اینکه تحت یک مجوز تجاری جداگانه مجاز شده باشد.

این موارد شامل، اما محدود به موارد زیر نیست:

- محصولات تجاری
- خدمات پولی
- SaaS تجاری
- توزیع تجاری
- صدور مجوز تجاری
- ادغام در سامانه‌های تجاری

کتابخانه‌ها، Datasetها، مدل‌های ازپیش‌آموزش‌دیده، APIها و سایر اجزای شخص ثالث تابع مجوزهای مربوط به خود هستند.

متن کامل مجوز:

""LICENSE.md"" (LICENSE.md)

---

👨‍💻 توسعه‌دهنده

Jupiter Code Team

Smart Electricity Consumption Prediction System

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

---

<div align="center">⚡ Research → Prototype → Product

Adaptive Intelligence for Electricity Consumption

</div>---

<a id="english"></a>

🇬🇧 English

📌 Overview

Smart Electricity Consumption Prediction System is a research-to-product project developed by Jupiter Code.

The project combines consumer behavior analysis, adaptive segmentation, machine learning, and real electricity measurement to develop a low-cost, locally developed, and practical energy-intelligence system.

Core Components

- ⚡ Electricity consumption forecasting
- 🧠 Behavior-aware adaptive segmentation
- 👥 User clustering
- 📊 Time-series analysis
- 🤖 Machine learning
- 📡 Real electricity measurement through IoT
- 🔄 Adaptation to changing consumption patterns

«Electricity consumption is not merely a numerical signal; it is a reflection of consumer behavior.»

---

🎯 Project Goal

We do not want this system to remain only a research idea.

The goal is to develop a real, low-cost, locally developed system for electricity measurement, analysis, and forecasting.

The project is simultaneously developing the algorithm, forecasting pipeline, measurement layer, and system integration so that the path from research to a usable system remains short.

Development Path

Research & Algorithm
        ↓
Real-Data Validation
        ↓
Integrated Prototype
        ↓
Low-Cost Product

The project is not positioned as a distant product concept. Its core algorithmic, forecasting, software, and measurement components are already being developed and integrated.

---

🧠 Behavior-Aware Adaptive Segmentation

The Problem

One of the first ideas that naturally comes to mind when segmenting electricity consumption is reducing within-segment variance.

This is conceptually related to approaches such as Fisher–Jenks Natural Breaks.

Jenks divides a 24-hour profile into four contiguous sections while minimizing within-segment dispersion, with boundaries computed once and then kept fixed.

However, this was not sufficient for our objective.

We did not want the system to answer only:

«Where is the variance lower?»

We wanted to investigate:

«Where does consumer behavior actually change, and is that change persistent and repeatable?»

Therefore, the project moved from a purely variance-oriented approach toward an adaptive, behavior-aware segmentation approach.

---

🔄 Adaptive Segmentation

For each day, only the previous 30 days are used.

Previous 30 Days
       ↓
Weighted Median
       ↓
Hourly Behavioral Profile
       ↓
Smoothing
       ↓
Change Analysis
       ↓
Persistence Evaluation
       ↓
Segment Constraints
       ↓
4 Contiguous Segments

Current Parameters

Parameter| Value
Number of segments| 4
Minimum length| 4 hours
Maximum length| 7 hours
Historical window| 30 days
Boundary update| Daily

The segmentation boundaries are recomputed daily based on recent user behavior.

---

📐 Recent-Behavior Weighting

Recent observations receive higher importance using:

w ∝ 0.97^age

The objective is to balance:

- responsiveness to recent behavioral changes
- robustness against noise and isolated observations

---

📊 Dataset & Evaluation

The current benchmark uses real-world Smart Meter London data.

Property| Value
Dataset| Smart Meter London
Households| 1,000
Period| December 2012 – December 2013
Split| Temporal
Training| 80%
Testing| 20%
Horizons| Day 1 / Day 2 / Day 3
Strategy| Direct Forecasting

The final 20% of the timeline is reserved for testing.

Why 80/20?

PAST                                      FUTURE

|------------- 80% -------------|---- 20% ---->
          Training                    Test

A random shuffle is not used because forecasting models should learn from past observations and be evaluated on future observations.

---

🤖 Forecasting

Random Forest

The current benchmark uses a global Random Forest with the segmentation methods being compared.

Evaluated horizons:

- Day 1
- Day 2
- Day 3

Random Forest is currently retained as the primary forecasting model.

---

📈 Benchmark Results

Adaptive Segmentation vs. Jenks

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²| Naive WAPE
Day 1| 18.31%| 18.34%| 0.856| 0.857| 25.28%
Day 2| 20.28%| 20.26%| 0.782| 0.774| 25.31%
Day 3| 21.36%| 21.36%| 0.605| 0.692| 25.42%

The WAPE values are very close between the two segmentation methods for the evaluated horizons.

The project therefore does not claim universal superiority across every metric. The focus is on evaluating whether adaptive, behavior-aware segmentation can maintain competitive forecasting performance while providing a dynamic behavioral representation.

More Challenging Devices

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²
Day 1| 24.64%| 23.73%| 0.837| 0.870
Day 2| 32.08%| 31.16%| 0.482| 0.418
Day 3| 37.21%| 33.95%| 0.824| -0.023

These results concern outlier devices or devices with shorter histories.

---

👥 User Clustering

User behavior is also analyzed through clustering.

Current results:

- 948 clustered devices
- 52 outlier devices
- 2 main clusters

The reported groups are:

- 🟢 Regular: 626 devices
- 🟠 High-variance: 321 devices

Approximate WAPE ranges are 15–17% for the regular group and 24–28% for the high-variance group.

---

🔬 Clustering Effect

The effect of clustering depends on the forecasting algorithm.

Model| Day 1| Day 2| Day 3
Ridge| +79.8%| +66.0%| +31.2%
Random Forest| -1.1%| -1.2%| -0.8%

The results show that clustering does not have the same effect across forecasting algorithms.

Clustering therefore remains an analytical and extensible component of the system.

---

🏗️ System Architecture

                 ┌─────────────────┐
                 │  Electricity    │
                 │      Data       │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Preprocessing   │
                 └────────┬────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Adaptive Segmentation │
              └───────────┬───────────┘
                          │
                 ┌────────┴────────┐
                 │                 │
                 ▼                 ▼
          User Clustering    Feature Engineering
                 │                 │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │  Random Forest  │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Consumption     │
                 │   Forecast      │
                 └─────────────────┘

---

📡 Low-Cost Hardware Prototype

The project also includes a real electricity measurement prototype.

Main Components

- ESP32
- CT Clamp
- B101ZMPT
- Wi-Fi

The updated hardware samples voltage and current simultaneously, enabling calculation of:

- RMS Voltage
- RMS Current
- Real Power
- Apparent Power
- Power Factor

The B101ZMPT was added to address the previous fixed-voltage assumption.

---

⚡ Measurement Pipeline

Electricity Grid
       │
       ├──────────────┐
       ▼              ▼
   CT Clamp       B101ZMPT
    Current         Voltage
       │              │
       └──────┬───────┘
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

The system calculates voltage, current, real power, apparent power, and power factor.

The current prototype sends a measurement package to the server every 10 seconds.

Example Payload

{
  "current_A": 2.145,
  "voltage_V": 228.4,
  "power_W": 478.2,
  "apparent_power_VA": 490.1,
  "power_factor": 0.976
}

---

🔧 Hardware Update

The initial prototype approximately assumed a 230 V supply.

The updated version:

- adds the B101ZMPT voltage sensor
- measures actual voltage
- samples voltage and current together
- calculates real power
- calculates apparent power
- calculates power factor

This change addresses the limitation of treating grid voltage as a fixed value.

---

🎯 Research → Product

The project follows a Research-to-Product approach.

Research
   ↓
Benchmark
   ↓
Integrated Prototype
   ↓
Low-Cost Product

The focus is on completing and integrating the existing components, rather than creating a long sequence of distant stages.

Final Objective

«A smart, low-cost, locally developed system for electricity measurement, analysis, and forecasting.»

---

🛣️ Roadmap

Forecasting

- [ ] Improve Day-1 accuracy
- [ ] Develop a dedicated Day-2 model
- [ ] Develop a dedicated Day-3 model
- [ ] Compare additional forecasting algorithms
- [ ] Evaluate horizon-specific forecasting

Adaptive Segmentation

- [ ] Improve behavioral change detection
- [ ] Improve persistence measurement
- [ ] Study seasonal behavior
- [ ] Investigate adaptive segment counts

Clustering

- [ ] Evaluate additional clustering methods
- [ ] Improve volatile-user detection
- [ ] Develop specialized behavioral models

Hardware

- [ ] Improve calibration
- [ ] Validate against reference instruments
- [ ] Improve reliability
- [ ] Improve physical design
- [ ] Reduce production cost

Product

- [ ] Complete hardware–forecasting integration
- [ ] Develop monitoring dashboard
- [ ] Complete backend integration
- [ ] Conduct field testing
- [ ] Prepare a usable product version

---

⚠️ Current Limitations

The project is under active development.

Current limitations include:

- Consumption behavior varies between users.
- Highly volatile users are more difficult to forecast.
- Day 2 and Day 3 require further development.
- The effect of clustering depends on the forecasting model.
- Hardware requires calibration and validation.
- The benchmark dataset does not represent every possible consumption pattern.

These limitations are part of the current research and development process.

---

🌱 Project Philosophy

«"Do not optimize only what is easy to measure; model what actually matters."»

Variance is useful, but variance alone does not necessarily describe consumer behavior.

The project therefore combines:

Statistics + Behavior + Adaptation + Machine Learning + Real Measurement

to build an electricity-intelligence system.

---

📚 Dataset

Smart Meter Energy Consumption Data in London Households

Source:

https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d

Dataset usage remains subject to the terms and license of the original source.

---

📺 Demonstration

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

A project demonstration with visual benchmark comparisons is available through the project channel.

---

📜 Citation

If substantial parts of this project are used in research, publications, presentations, competitions, academic projects, or derivative projects, please provide attribution:

«Smart Electricity Consumption Prediction System
Jupiter Code / Mohammad Mahdi Vafri»

---

⚖️ Copyright & License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

This project is released under:

Jupiter Code Non-Commercial License v1.1

Permitted Non-Commercial Use

- Personal use
- Educational use
- Academic use
- Scientific use
- Research use
- Other permitted non-commercial use under the License

Commercial Use

Commercial use requires prior written permission from the Copyright Holder, unless separately authorized under a commercial license.

This includes, but is not limited to:

- Commercial products
- Paid services
- Commercial SaaS
- Commercial redistribution
- Commercial licensing
- Integration into commercial systems

Third-party libraries, datasets, pretrained models, APIs, and other external components remain subject to their respective licenses.

Full License:

""LICENSE.md"" (LICENSE.md)

---

👨‍💻 Author

Jupiter Code Team

Smart Electricity Consumption Prediction System

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

---

<div align="center">⚡ Research → Prototype → Product

Adaptive Intelligence for Electricity Consumption

</div>