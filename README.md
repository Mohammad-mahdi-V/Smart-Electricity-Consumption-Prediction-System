<div align="center">⚡ سامانه هوشمند پیش‌بینی مصرف برق

Smart Electricity Consumption Prediction System

<p>
  <b>سگمنت‌بندی تطبیقی مبتنی بر رفتار • یادگیری ماشین • IoT • هوش انرژی</b>
</p><p>
  <a href="#فارسی">🇮🇷 فارسی</a>
  &nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="#english">🇬🇧 English</a>
</p></div>---

<a id="فارسی"></a>

🇮🇷 فارسی

📌 معرفی پروژه

سامانه هوشمند پیش‌بینی مصرف برق یک پروژه پژوهشی و محصول‌محور است که توسط Jupiter Code توسعه داده می‌شود.

هدف پروژه ترکیب تحلیل رفتار مصرف‌کننده، سگمنت‌بندی تطبیقی، یادگیری ماشین و اندازه‌گیری واقعی برق برای توسعه یک سامانه کم‌هزینه و بومی در حوزه هوش انرژی است.

اجزای اصلی

حوزه| توضیح
⚡ پیش‌بینی| پیش‌بینی مصرف برق در افق‌های مختلف
🧠 سگمنت‌بندی| تقسیم تطبیقی پروفایل مصرف بر اساس رفتار
👥 خوشه‌بندی| شناسایی گروه‌های رفتاری کاربران
📊 تحلیل داده| تحلیل سری زمانی و استخراج ویژگی
🤖 یادگیری ماشین| استفاده از مدل‌های ML برای پیش‌بینی
📡 IoT| اندازه‌گیری واقعی ولتاژ و جریان
🔄 سازگاری| واکنش به تغییرات الگوی مصرف

«مصرف برق فقط یک سیگنال عددی نیست؛ بلکه بازتابی از رفتار مصرف‌کننده است.»

---

🎯 چشم‌انداز و هدف پروژه

ما نمی‌خواهیم این سامانه صرفاً به‌عنوان یک ایده پژوهشی باقی بماند.

هدف پروژه، توسعه یک سامانه واقعی، کم‌هزینه و بومی برای پایش و پیش‌بینی مصرف برق است که بتواند از داده‌های واقعی برق استفاده کرده و در محیط واقعی مورد استفاده قرار گیرد.

تمرکز فعلی پروژه روی تکمیل و یکپارچه‌سازی اجزای اصلی سامانه است:

بخش| هدف
🧠 سگمنت‌بندی تطبیقی| توسعه و ارزیابی الگوریتم رفتارمحور
🤖 پیش‌بینی مصرف| بهبود و ارزیابی مدل‌های پیش‌بینی
👥 خوشه‌بندی کاربران| استخراج الگوهای رفتاری
📡 اندازه‌گیری واقعی| توسعه نمونه سخت‌افزاری کم‌هزینه
💻 سامانه نرم‌افزاری| یکپارچه‌سازی اجزای سامانه
🚀 محصول| آماده‌سازی برای استفاده واقعی

مسیر پروژه

Research & Algorithm
        │
        ▼
Benchmark & Validation
        │
        ▼
Integrated Prototype
        │
        ▼
Low-Cost Product

بنابراین فاصله پروژه تا محصول به‌عنوان یک مسیر طولانی و جداگانه تعریف نشده است؛ نمونه اولیه، الگوریتم، بخش نرم‌افزاری و بخش اندازه‌گیری در حال توسعه هم‌زمان هستند تا مستقیماً به یک سامانه قابل استفاده تبدیل شوند.

---

🧠 سگمنت‌بندی تطبیقی مبتنی بر رفتار

مسئله اصلی

یکی از اولین ایده‌هایی که هنگام فکر کردن به سگمنت‌بندی مصرف برق به ذهن می‌رسد، کاهش واریانس درون سگمنت‌ها است.

این ایده از نظر مفهومی به روش‌هایی مانند Fisher–Jenks Natural Breaks نزدیک است.

در روش Jenks، روز ۲۴ ساعته به چهار بخش پیوسته تقسیم می‌شود تا پراکندگی درون بخش‌ها کاهش پیدا کند و مرزها پس از محاسبه ثابت باقی می‌مانند.

اما برای مسئله ما این کافی نبود.

ما نمی‌خواستیم سامانه فقط پاسخ دهد:

«کجا واریانس کمتر است؟»

بلکه می‌خواستیم بررسی کند:

«رفتار مصرف‌کننده کجا واقعاً تغییر می‌کند و آیا این تغییر پایدار و تکرارشونده است؟»

به همین دلیل، روش پروژه از یک رویکرد صرفاً مبتنی بر پراکندگی به سمت یک رویکرد تطبیقی و رفتارمحور توسعه داده شده است.

---

🔄 فرایند سگمنت‌بندی

سامانه برای هر روز از پنجره ۳۰ روز قبل استفاده می‌کند و مرزهای سگمنت‌ها را به‌صورت روزانه محاسبه می‌کند.

مرحله| عملیات
1| ساخت پروفایل ساعتی مصرف
2| استفاده از Weighted Median
3| وزن‌دهی بیشتر به روزهای اخیر
4| هموارسازی پروفایل
5| شناسایی تغییرات رفتاری
6| بررسی شدت و پایداری تغییر
7| اعمال محدودیت طول سگمنت
8| ایجاد چهار سگمنت پیوسته
9| محاسبه مجدد مرزها در هر روز

پارامترهای فعلی

پارامتر| مقدار
تعداد سگمنت| ۴
حداقل طول سگمنت| ۴ ساعت
حداکثر طول سگمنت| ۷ ساعت
پنجره تاریخی| ۳۰ روز
به‌روزرسانی مرزها| روزانه

---

📐 پروفایل رفتاری

برای توجه بیشتر به رفتارهای جدیدتر، از وزن‌دهی کاهشی استفاده می‌شود:

[
w \propto 0.97^{age}
]

ساختار پردازش:

ورودی| پردازش| خروجی
داده تاریخی| وزن‌دهی زمانی| داده وزن‌دار
داده وزن‌دار| Weighted Median| پروفایل ساعتی
پروفایل ساعتی| Smoothing| پروفایل پایدارتر
پروفایل| Change Analysis| تغییرات رفتاری
تغییرات| Constraints| مرز سگمنت‌ها

هدف این طراحی ایجاد تعادل میان:

- واکنش به تغییرات جدید رفتار
- مقاومت در برابر نویز و مشاهدات غیرعادی

---

📊 داده و روش ارزیابی

Benchmark فعلی روی داده واقعی Smart Meter London انجام شده است.

ویژگی| مقدار
Dataset| Smart Meter London
تعداد خانوار| ۱۰۰۰
بازه زمانی| دسامبر ۲۰۱۲ تا دسامبر ۲۰۱۳
نوع تقسیم| زمانی
آموزش| ۸۰٪
آزمون| ۲۰٪
افق پیش‌بینی| Day 1 / Day 2 / Day 3
استراتژی پیش‌بینی| Direct Forecasting

تقسیم آموزش و آزمون زمانی است و ۲۰٪ پایانی داده‌ها برای آزمون استفاده شده‌اند.

چرا ۸۰/۲۰؟

بخش| سهم| کاربرد
Training| ۸۰٪| آموزش مدل
Test| ۲۰٪| ارزیابی روی آینده دیده‌نشده

در مسئله پیش‌بینی سری زمانی، تقسیم زمانی از تقسیم تصادفی مناسب‌تر است، زیرا مدل باید از گذشته یاد بگیرد و روی داده‌های آینده ارزیابی شود.

---

🤖 مدل پیش‌بینی

مدل اصلی فعلی پروژه:

Random Forest

در Benchmark فعلی، یک Random Forest سراسری با دو روش سگمنت‌بندی مقایسه شده است.

ویژگی| مقدار
مدل اصلی| Random Forest
Horizon 1| Day 1
Horizon 2| Day 2
Horizon 3| Day 3
Strategy| Direct Forecasting

بر اساس نتایج Benchmark، Random Forest به‌عنوان روش اصلی پروژه انتخاب شده است.

---

📈 نتایج Benchmark

Adaptive Segmentation در برابر Jenks

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²| Naive WAPE
Day 1| 18.31%| 18.34%| 0.856| 0.857| 25.28%
Day 2| 20.28%| 20.26%| 0.782| 0.774| 25.31%
Day 3| 21.36%| 21.36%| 0.605| 0.692| 25.42%

نتایج Benchmark نشان می‌دهند که عملکرد دو روش در WAPE بسیار نزدیک است؛ تفاوت اصلی در برخی شرایط سخت‌تر و در پایداری مدل مشاهده می‌شود.

در تحلیل پروژه، سگمنت‌بندی تطبیقی به دلیل حفظ عملکرد رقابتی و رفتار بهتر در برخی شرایط دشوار، در کنار Random Forest نگه داشته شده است.

عملکرد روی دستگاه‌های سخت‌تر

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²
Day 1| 24.64%| 23.73%| 0.837| 0.870
Day 2| 32.08%| 31.16%| 0.482| 0.418
Day 3| 37.21%| 33.95%| 0.824| 0.023

این بخش برای بررسی رفتار روش‌ها روی دستگاه‌های پرت یا دارای سابقه کوتاه ارائه شده است.

---

👥 خوشه‌بندی کاربران

پس از بررسی نتایج، خوشه‌بندی کاربران نیز به پروژه اضافه و با حالت بدون خوشه مقایسه شده است.

وضعیت فعلی

شاخص| مقدار
دستگاه‌های خوشه‌بندی‌شده| ۹۴۸
دستگاه‌های پرت| ۵۲
تعداد خوشه| K = 2

دو الگوی اصلی شناسایی شده‌اند:

خوشه| تعداد دستگاه| WAPE تقریبی
منظم| ۶۲۶| حدود ۱۵٪ تا ۱۷٪
پرنوسان| ۳۲۱| حدود ۲۴٪ تا ۲۸٪

---

🔬 اثر خوشه‌بندی بر مدل‌ها

اثر خوشه‌بندی به الگوریتم پیش‌بینی وابسته است.

Model| Day 1| Day 2| Day 3
Ridge| +79.8%| +66.0%| +31.2%
Random Forest| −1.1%| −1.2%| −0.8%

نتایج نشان می‌دهند که خوشه‌بندی برای مدل‌های مختلف اثر یکسانی ندارد. در مستندات پروژه، اثر قابل‌توجه خوشه‌بندی برای Ridge و اثر محدودتر آن برای Random Forest گزارش شده است.

---

🏗️ معماری سامانه

برای اینکه README در GitHub روی دسکتاپ و موبایل مرتب نمایش داده شود، معماری اصلی به‌صورت جدول ارائه می‌شود:

لایه| وظیفه
📥 Data| دریافت داده مصرف
🧹 Preprocessing| آماده‌سازی داده
🧠 Adaptive Segmentation| استخراج ساختار رفتاری
👥 User Clustering| گروه‌بندی کاربران
📊 Feature Engineering| استخراج ویژگی
🤖 Random Forest| پیش‌بینی
📈 Evaluation| ارزیابی عملکرد

جریان اصلی سامانه

Data
  ↓
Preprocessing
  ↓
Adaptive Segmentation
  ↓
Feature Engineering
  ↓
Random Forest
  ↓
Consumption Forecast

تحلیل رفتاری

Adaptive Segmentation
        ├── Behavioral Profile
        └── User Clustering

---

📡 نمونه سخت‌افزاری کم‌هزینه

پروژه در کنار بخش نرم‌افزاری، نمونه اولیه اندازه‌گیری واقعی برق را نیز توسعه داده است.

قطعه| نقش
ESP32| پردازش و ارتباط
CT Clamp| اندازه‌گیری جریان
B101ZMPT| اندازه‌گیری ولتاژ
Wi-Fi| انتقال داده

در نسخه جدید، ولتاژ واقعی نیز در کنار جریان نمونه‌برداری می‌شود تا محاسبه توان واقعی به شرایط شبکه نزدیک‌تر باشد.

---

⚡ اندازه‌گیری برق

پارامترهای اندازه‌گیری

پارامتر| خروجی
RMS Voltage| "Vrms"
RMS Current| "Irms"
Real Power| "W"
Apparent Power| "VA"
Power Factor| "PF"

در نسخه اولیه ولتاژ حدود ۲۳۰ ولت فرض می‌شد؛ در نسخه جدید سنسور ولتاژ B101ZMPT اضافه شده و ولتاژ و جریان به‌صورت همزمان نمونه‌برداری می‌شوند.

---

📡 مسیر داده سخت‌افزار

مرحله| Component| خروجی
1| ⚡ شبکه برق| سیگنال برق
2| CT Clamp| جریان
3| B101ZMPT| ولتاژ
4| ESP32| پردازش محلی
5| Wi-Fi| انتقال داده
6| Server| دریافت داده
7| AI / Forecasting| تحلیل و پیش‌بینی

نمونه پیام

{
  "current_A": 2.145,
  "voltage_V": 228.4,
  "power_W": 478.2,
  "apparent_power_VA": 490.1,
  "power_factor": 0.976
}

بسته داده طبق مستندات پروژه هر ۱۰ ثانیه به سرور ارسال می‌شود.

---

🎯 Research → Product

پروژه با نگاه Research-to-Product توسعه داده می‌شود، اما مسیر محصول عمداً کوتاه نگه داشته شده است:

وضعیت| تمرکز
🔬 Research| توسعه روش
🧪 Benchmark| اعتبارسنجی روی داده واقعی
🔧 Prototype| تکمیل نمونه عملی
🚀 Product| یکپارچه‌سازی و استفاده واقعی

هدف نهایی

یک سامانه هوشمند، کم‌هزینه و بومی برای اندازه‌گیری، تحلیل و پیش‌بینی مصرف برق.

هدف این نیست که پروژه سال‌ها در مرحله تحقیق باقی بماند؛ بخش پژوهشی مستقیماً برای تکمیل نمونه عملی و نزدیک شدن به محصول قابل استفاده به کار گرفته می‌شود.

---

🛣️ نقشه راه

⚡ پیش‌بینی

- [ ] بهبود دقت Day 1
- [ ] توسعه مدل‌های اختصاصی برای Day 2 و Day 3
- [ ] مقایسه مدل‌های مختلف
- [ ] بررسی Direct و Horizon-Specific Forecasting

🧠 سگمنت‌بندی

- [ ] بهبود تشخیص تغییرات رفتاری
- [ ] بررسی معیارهای پایداری
- [ ] بررسی رفتار فصلی
- [ ] بررسی تعداد سگمنت‌های تطبیقی

👥 خوشه‌بندی

- [ ] مقایسه روش‌های بیشتر
- [ ] تشخیص بهتر کاربران پرنوسان
- [ ] توسعه مدل‌های تخصصی گروه‌ها

📡 سخت‌افزار

- [ ] بهبود کالیبراسیون
- [ ] مقایسه با ابزارهای مرجع
- [ ] افزایش قابلیت اطمینان
- [ ] بهبود طراحی فیزیکی
- [ ] کاهش هزینه ساخت

🚀 یکپارچه‌سازی محصول

- [ ] اتصال کامل سخت‌افزار و مدل پیش‌بینی
- [ ] توسعه داشبورد
- [ ] اتصال پایدار Backend و دستگاه
- [ ] تست میدانی
- [ ] آماده‌سازی نسخه قابل استفاده

---

⚠️ محدودیت‌های فعلی

محدودیت| توضیح
رفتار کاربران| الگوهای مصرف متفاوت هستند
کاربران پرنوسان| پیش‌بینی دشوارتر است
Day 2 / Day 3| نیازمند توسعه بیشتر
Clustering| اثر آن به مدل پیش‌بینی وابسته است
Hardware| نیازمند کالیبراسیون و اعتبارسنجی
Dataset| تمام الگوهای مصرف ممکن را پوشش نمی‌دهد

---

🌱 فلسفه پروژه

««فقط چیزی را که اندازه‌گیری آن آسان است بهینه نکن؛ چیزی را مدل کن که واقعاً اهمیت دارد.»»

واریانس یک معیار مهم است، اما واریانس به‌تنهایی لزوماً رفتار مصرف‌کننده را توصیف نمی‌کند.

رویکرد پروژه ترکیبی از:

حوزه| نقش
Statistics| تحلیل پراکندگی
Behavior| شناخت رفتار مصرف
Adaptation| واکنش به تغییرات
Machine Learning| پیش‌بینی
IoT| اندازه‌گیری واقعی

است.

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

نوع استفاده| وضعیت
استفاده شخصی| ✅ مجاز طبق شرایط مجوز
آموزشی| ✅ مجاز طبق شرایط مجوز
دانشگاهی| ✅ مجاز طبق شرایط مجوز
علمی| ✅ مجاز طبق شرایط مجوز
پژوهشی| ✅ مجاز طبق شرایط مجوز
استفاده تجاری| ⚠️ نیازمند اجازه کتبی

استفاده تجاری شامل، اما محدود به موارد زیر نیست:

- محصولات تجاری
- خدمات پولی
- SaaS تجاری
- توزیع تجاری
- صدور مجوز تجاری
- ادغام در سامانه‌های تجاری

کتابخانه‌ها، دیتاست‌ها، مدل‌های ازپیش‌آموزش‌دیده، APIها و سایر اجزای شخص ثالث تابع مجوزهای مربوط به خود هستند.

متن کامل مجوز:

""LICENSE.md"" (LICENSE.md)

---

👨‍💻 توسعه‌دهنده

Jupiter Code Team

Smart Electricity Consumption Prediction System

© 2026 Jupiter Code / Mohammad Mahdi Vafri

---

<a id="english"></a>

🇬🇧 English

📌 Overview

Smart Electricity Consumption Prediction System is a research-to-product project developed by Jupiter Code.

The project combines consumer behavior analysis, adaptive segmentation, machine learning, and real electricity measurement to develop a low-cost and locally developed energy-intelligence system.

Core Components

Area| Description
⚡ Forecasting| Electricity consumption forecasting
🧠 Segmentation| Behavior-aware adaptive segmentation
👥 Clustering| Behavioral user grouping
📊 Data Analysis| Time-series analysis and feature extraction
🤖 Machine Learning| ML-based forecasting
📡 IoT| Real electricity measurement
🔄 Adaptation| Response to changing consumption patterns

«Electricity consumption is not merely a numerical signal; it is a reflection of consumer behavior.»

---

🎯 Project Vision & Goal

We do not want this system to remain only a research idea.

The goal is to develop a real, low-cost, locally developed electricity monitoring and forecasting system that can use real electricity measurements and operate in practical environments.

The current focus is on completing and integrating the core components:

Component| Goal
🧠 Adaptive Segmentation| Develop and evaluate behavior-aware segmentation
🤖 Forecasting| Improve and evaluate forecasting models
👥 User Clustering| Extract behavioral patterns
📡 Real Measurement| Develop low-cost measurement hardware
💻 Software System| Integrate the system components
🚀 Product| Prepare the system for real-world use

Project Path

Research & Algorithm
        │
        ▼
Benchmark & Validation
        │
        ▼
Integrated Prototype
        │
        ▼
Low-Cost Product

The project is therefore not positioned as a long sequence of distant stages. The algorithm, software, forecasting pipeline, and measurement prototype are being developed together toward a usable product.

---

🧠 Behavior-Aware Adaptive Segmentation

The Core Problem

One of the first ideas that naturally comes to mind when segmenting electricity consumption is reducing within-segment variance.

Conceptually, this is related to methods such as Fisher–Jenks Natural Breaks.

Jenks divides the 24-hour profile into four contiguous sections while minimizing within-segment dispersion, with boundaries computed and then kept fixed.

However, that was not sufficient for our objective.

We did not want the system to answer only:

«Where is the variance lower?»

We wanted it to investigate:

«Where does consumer behavior actually change, and is that change persistent and meaningful?»

Therefore, the project moved from a purely variance-oriented approach toward an adaptive, behavior-aware approach.

---

🔄 Adaptive Segmentation Pipeline

For each day, the system uses the previous 30-day window and recomputes the segmentation boundaries daily.

Step| Operation
1| Build hourly consumption profile
2| Apply Weighted Median
3| Give more weight to recent days
4| Smooth the profile
5| Detect behavioral changes
6| Evaluate change strength
7| Evaluate persistence
8| Apply segment-length constraints
9| Generate four contiguous segments
10| Recompute boundaries daily

Current Parameters

Parameter| Value
Number of segments| 4
Minimum segment length| 4 hours
Maximum segment length| 7 hours
Historical window| 30 days
Boundary update| Daily

---

📐 Behavioral Profile

Recent observations receive higher importance using:

[
w \propto 0.97^{age}
]

Input| Processing| Output
Historical data| Temporal weighting| Weighted data
Weighted data| Weighted Median| Hourly profile
Hourly profile| Smoothing| Stable profile
Profile| Change Analysis| Behavioral changes
Changes| Constraints| Segment boundaries

The goal is to balance responsiveness to recent behavior with robustness against noise and isolated abnormal observations.

---

📊 Dataset & Evaluation

Property| Value
Dataset| Smart Meter London
Households| 1,000
Period| December 2012 – December 2013
Split| Temporal
Training| 80%
Testing| 20%
Forecast Horizons| Day 1 / Day 2 / Day 3
Forecast Strategy| Direct Forecasting

The benchmark uses a chronological split, with the final 20% of the timeline reserved for testing.

Why 80/20?

Split| Share| Purpose
Training| 80%| Model training
Testing| 20%| Future-data evaluation

A temporal split is used instead of a random split because the forecasting model should learn from the past and be evaluated on future observations.

---

🤖 Forecasting Model

Random Forest

The current benchmark uses a global Random Forest with the segmentation methods being compared.

Property| Value
Primary model| Random Forest
Horizon 1| Day 1
Horizon 2| Day 2
Horizon 3| Day 3
Strategy| Direct Forecasting

Based on the benchmark results, Random Forest is retained as the primary forecasting model.

---

📈 Benchmark Results

Adaptive Segmentation vs. Jenks

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²| Naive WAPE
Day 1| 18.31%| 18.34%| 0.856| 0.857| 25.28%
Day 2| 20.28%| 20.26%| 0.782| 0.774| 25.31%
Day 3| 21.36%| 21.36%| 0.605| 0.692| 25.42%

The benchmark shows very similar WAPE values between the two segmentation approaches. The project analysis focuses on the additional behavioral and stability characteristics of adaptive segmentation rather than claiming universal superiority.

---

👥 User Clustering

User clustering was added following the evaluation process and compared with the non-clustered approach.

Current Results

Metric| Value
Clustered devices| 948
Outlier devices| 52
Number of clusters| K = 2

Cluster| Devices| Approx. WAPE
Regular| 626| 15%–17%
High-variance| 321| 24%–28%

---

🔬 Clustering Effect

The effect of clustering depends on the forecasting algorithm.

Model| Day 1| Day 2| Day 3
Ridge| +79.8%| +66.0%| +31.2%
Random Forest| −1.1%| −1.2%| −0.8%

The reported results show that clustering does not affect all forecasting algorithms in the same way.

---

🏗️ System Architecture

Layer| Function
📥 Data| Consumption data
🧹 Preprocessing| Data preparation
🧠 Adaptive Segmentation| Behavioral structure
👥 User Clustering| User grouping
📊 Feature Engineering| Feature extraction
🤖 Random Forest| Forecasting
📈 Evaluation| Performance evaluation

Main Pipeline

Data
  ↓
Preprocessing
  ↓
Adaptive Segmentation
  ↓
Feature Engineering
  ↓
Random Forest
  ↓
Consumption Forecast

Behavioral Analysis

Adaptive Segmentation
        ├── Behavioral Profile
        └── User Clustering

---

📡 Low-Cost Hardware Prototype

Component| Role
ESP32| Processing and communication
CT Clamp| Current measurement
B101ZMPT| Voltage measurement
Wi-Fi| Data transmission

The updated hardware measures voltage and current simultaneously, allowing real power, apparent power, and power factor to be calculated.

---

⚡ Electricity Measurement

Measurements

Parameter| Output
RMS Voltage| "Vrms"
RMS Current| "Irms"
Real Power| "W"
Apparent Power| "VA"
Power Factor| "PF"

The initial prototype assumed approximately 230 V. The updated version adds the B101ZMPT voltage sensor and samples voltage and current simultaneously.

---

📡 Hardware Data Flow

Stage| Component| Output
1| ⚡ Electrical Grid| Electrical signal
2| CT Clamp| Current
3| B101ZMPT| Voltage
4| ESP32| Local processing
5| Wi-Fi| Data transmission
6| Server| Data reception
7| AI / Forecasting| Analysis and prediction

Example Payload

{
  "current_A": 2.145,
  "voltage_V": 228.4,
  "power_W": 478.2,
  "apparent_power_VA": 490.1,
  "power_factor": 0.976
}

The current firmware sends a measurement package to the server every 10 seconds.

---

🎯 Research → Product

The project follows a Research-to-Product approach with a deliberately short path toward practical deployment.

Stage| Focus
🔬 Research| Develop the methodology
🧪 Benchmark| Validate using real data
🔧 Prototype| Complete the working system
🚀 Product| Integrate and deploy

Final Objective

A smart, low-cost, locally developed system for electricity measurement, analysis, and forecasting.

Research is not treated as a separate destination; it directly supports the completion and improvement of the practical system.

---

🛣️ Roadmap

⚡ Forecasting

- [ ] Improve Day-1 forecasting
- [ ] Develop specialized Day-2 and Day-3 models
- [ ] Compare additional forecasting algorithms
- [ ] Compare Direct and Horizon-Specific Forecasting

🧠 Adaptive Segmentation

- [ ] Improve behavioral change detection
- [ ] Investigate persistence measures
- [ ] Study seasonal behavior
- [ ] Investigate adaptive segment counts

👥 Clustering

- [ ] Evaluate additional clustering methods
- [ ] Improve volatile-user detection
- [ ] Develop specialized behavioral models

📡 Hardware

- [ ] Improve calibration
- [ ] Validate against reference instruments
- [ ] Improve reliability
- [ ] Improve physical design
- [ ] Reduce production cost

🚀 Product Integration

- [ ] Complete hardware–forecasting integration
- [ ] Develop monitoring dashboard
- [ ] Connect backend and measurement device
- [ ] Conduct field testing
- [ ] Prepare a usable product version

---

⚠️ Current Limitations

Limitation| Description
User behavior| Consumption patterns vary between users
Volatile users| More difficult to forecast
Day 2 / Day 3| Requires further development
Clustering| Effect depends on forecasting model
Hardware| Requires calibration and validation
Dataset| Does not cover every possible consumption pattern

---

🌱 Project Philosophy

«"Do not optimize only what is easy to measure; model what actually matters."»

Variance is an important statistical measure, but variance alone does not necessarily describe consumer behavior.

The project therefore combines:

Domain| Role
Statistics| Measure dispersion
Behavior| Understand consumption
Adaptation| Respond to changes
Machine Learning| Forecast consumption
IoT| Measure real electricity

---

📚 Dataset

Benchmark dataset:

Smart Meter Energy Consumption Data in London Households

Source:

https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d

Dataset usage remains subject to the terms and license of the original data source.

---

📺 Demonstration

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

---

📜 Citation

If substantial parts of this project are used in research, publications, presentations, competitions, academic projects, or derivative works, please provide attribution:

«Smart Electricity Consumption Prediction System
Jupiter Code / Mohammad Mahdi Vafri»

---

⚖️ Copyright / License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

This project is released under:

Jupiter Code Non-Commercial License v1.1

Usage| Status
Personal| ✅ Permitted under the License
Educational| ✅ Permitted under the License
Academic| ✅ Permitted under the License
Scientific| ✅ Permitted under the License
Research| ✅ Permitted under the License
Commercial| ⚠️ Requires written permission

Commercial use includes, but is not limited to:

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

© 2026 Jupiter Code / Mohammad Mahdi Vafri

---

<div align="center">⚡ Research → Prototype → Product

Adaptive Intelligence for Electricity Consumption

</div>