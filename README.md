
یک سخن صمیمی !:
ui با تغییرات جدید هاهنگ نشده است
----------------------------------------------------------------------
درمورد سگمنشن اولین ایده که به ذهن انسان میرشود کاهش وایانس در سگمنت ها است چیزی مشابه jenks و ما نیز در نخست این ایده به ذهنمان رسیده بود 
اما این روش به بقیه پارمتر های رفتاری کاربر توجه ندارد و به کاهش واریانس بسنده میکند و ما این را نمی خواستیم پس ان را تغییر دادیم
ما نمیخواهیم این سامانه به عنوان یک ایده باقی بماند میخواهیم ان را تبدیل به یک محصول بومی کم هزینه تبدیل کنیم


<div align="center">⚡ سامانه هوشمند پیش‌بینی مصرف برق

Smart Electricity Consumption Prediction System

Adaptive Segmentation • Machine Learning • IoT • Energy Intelligence

<br><a href="#فارسی">🇮🇷 فارسی</a>
  •  
<a href="#english">🇬🇧 English</a>

</div>---

<a id="فارسی"></a>

🇮🇷 فارسی

📌 معرفی

سامانه هوشمند پیش‌بینی مصرف برق یک پروژه پژوهشی و محصول‌محور است که توسط Jupiter Code توسعه داده می‌شود.

هدف پروژه ترکیب:

- 🧠 تحلیل رفتار مصرف‌کننده
- 📊 سگمنت‌بندی تطبیقی
- 🤖 یادگیری ماشین
- 👥 خوشه‌بندی کاربران
- 📡 اندازه‌گیری واقعی برق با IoT

برای توسعه یک سامانه بومی، کم‌هزینه و قابل توسعه برای پایش، تحلیل و پیش‌بینی مصرف برق است.

---

🧠 ایده اصلی

یکی از نخستین ایده‌ها در سگمنت‌بندی مصرف برق، کاهش واریانس درون سگمنت‌ها است؛ رویکردی که از نظر مفهومی به روش‌هایی مانند Fisher–Jenks نزدیک است.

اما کاهش واریانس به‌تنهایی برای مسئله ما کافی نبود.

ما نمی‌خواستیم سامانه فقط به این سؤال پاسخ دهد:

««کجا واریانس کمتر است؟»»

بلکه هدف این است که بررسی شود:

««رفتار مصرف‌کننده در کجا تغییر می‌کند و آیا این تغییر پایدار و معنادار است؟»»

به همین دلیل، سگمنت‌بندی پروژه به سمت یک رویکرد تطبیقی و رفتارمحور توسعه داده شده است.

---

🔄 سگمنت‌بندی تطبیقی

سامانه با استفاده از داده‌های ۳۰ روز گذشته، یک نمای رفتاری از مصرف‌کننده ایجاد می‌کند.

فرایند کلی:

داده‌های مصرف
      ↓
پروفایل ساعتی
      ↓
وزن‌دهی به داده‌های اخیر
      ↓
میانه وزندار
      ↓
کاهش نویز
      ↓
تشخیص تغییر رفتار
      ↓
بررسی پایداری تغییر
      ↓
تعیین مرز سگمنت‌ها
      ↓
به‌روزرسانی روزانه

پارامترهای فعلی:

- ۴ سگمنت پیوسته
- حداقل طول سگمنت: ۴ ساعت
- حداکثر طول سگمنت: ۷ ساعت
- پنجره تاریخی: ۳۰ روز
- به‌روزرسانی: روزانه
- وزن‌دهی داده‌های اخیر: "w ∝ 0.97^age"

---

🤖 پیش‌بینی مصرف

مدل اصلی فعلی:

Random Forest

افق‌های مورد بررسی:

- Day 1
- Day 2
- Day 3

تقسیم داده‌ها به‌صورت زمانی انجام می‌شود:

گذشته                                      آینده
──────────────────────────────────────────────────►

|--------------- 80% ---------------|--- 20% ---|
              آموزش                       آزمون

هدف این تقسیم‌بندی، ارزیابی مدل روی داده‌های آینده و جلوگیری از نشت اطلاعات زمانی است.

جزئیات کامل روش ارزیابی و نتایج در مستندات Word پروژه ارائه شده است.

---

👥 خوشه‌بندی کاربران

در کنار سگمنت‌بندی زمانی، رفتار کاربران نیز تحلیل و خوشه‌بندی می‌شود.

این بخش برای ایجاد زیرساختی جهت:

- پروفایل رفتاری کاربران
- پیش‌بینی شخصی‌سازی‌شده
- مدل‌های اختصاصی گروه‌ها
- انتخاب مدل مناسب برای گروه‌های مختلف

در نظر گرفته شده است.

---

📡 سخت‌افزار IoT

پروژه تنها به بخش نرم‌افزاری محدود نیست و یک نمونه اولیه برای اندازه‌گیری واقعی برق نیز در حال توسعه است.

اجزای اصلی:

- ESP32
- CT Clamp
- B101ZMPT
- Wi-Fi

پارامترهای اندازه‌گیری:

RMS Voltage
RMS Current
Real Power
Apparent Power
Power Factor

داده‌های اندازه‌گیری‌شده می‌توانند از طریق Wi-Fi به زیرساخت پردازش و پیش‌بینی منتقل شوند.

---

🏗️ معماری کلی

                 ┌─────────────────────┐
                 │   Electricity Data  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │  Data Preprocessing │
                 └──────────┬──────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ Adaptive Behavioral       │
              │ Segmentation              │
              └─────────────┬─────────────┘
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
          ┌──────────────┐     ┌──────────────┐
          │   Clustering │     │   Features   │
          └──────┬───────┘     └──────┬───────┘
                 │                    │
                 └─────────┬──────────┘
                           ▼
                  ┌─────────────────┐
                  │  Random Forest  │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   Forecasting   │
                  └─────────────────┘

---

🎯 هدف پروژه

هدف پروژه توسعه یک محصول بومی، کم‌هزینه و قابل استفاده برای پایش، تحلیل و پیش‌بینی مصرف برق است.

تمرکز پروژه از ابتدا فقط روی یک الگوریتم یا یک آزمایش پژوهشی نبوده است؛ بخش‌های مختلف سامانه به‌صورت هم‌زمان در حال توسعه و یکپارچه‌سازی هستند.

پژوهش
  ↓
الگوریتم
  ↓
نمونه یکپارچه
  ↓
محصول کم‌هزینه

هدف، نزدیک نگه‌داشتن مسیر توسعه به یک سامانه قابل استفاده واقعی است.

---

📄 مستندات کامل

جزئیات فنی پروژه در فایل Word مستندات پروژه ارائه شده است.

مستندات شامل مواردی مانند:

- الگوریتم کامل سگمنت‌بندی
- منطق Adaptive Segmentation
- مقایسه روش‌های سگمنت‌بندی
- روش ارزیابی مدل
- تحلیل خوشه‌بندی
- طراحی سخت‌افزار
- مدار و شماتیک
- روش اندازه‌گیری و کالیبراسیون
- ساختار Firmware
- ساختار داده‌های ارسالی
- برنامه توسعه محصول

«📘 برای مطالعه جزئیات کامل پروژه، به فایل Word مستندات مراجعه کنید.»

---

📚 Dataset

داده مورد استفاده در بخش پژوهشی پروژه:

Smart Meter Energy Consumption Data in London Households

استفاده از Dataset تابع شرایط و مجوز منبع اصلی داده است.

---

📺 نمایش پروژه

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

---

⚖️ Copyright & License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

این پروژه تحت:

Jupiter Code Non-Commercial License

منتشر شده است.

استفاده شخصی، آموزشی، دانشگاهی، علمی و پژوهشی مطابق شرایط License مجاز است.

استفاده تجاری نیازمند اجازه کتبی صاحب حق است، مگر اینکه تحت مجوز تجاری جداگانه مجاز شده باشد.

اجزای شخص ثالث، Datasetها، کتابخانه‌ها، مدل‌ها و وابستگی‌های خارجی تابع مجوزهای مربوط به خود هستند.

جزئیات کامل:

""LICENSE.md"" (LICENSE.md)

---

<a id="english"></a>

🇬🇧 English

📌 Overview

Smart Electricity Consumption Prediction System is a research-to-product project developed by Jupiter Code.

The project combines:

- 🧠 Consumer behavior analysis
- 📊 Adaptive segmentation
- 🤖 Machine learning
- 👥 User clustering
- 📡 Real electricity measurement using IoT

to develop a low-cost, locally developed, and scalable electricity monitoring, analysis, and forecasting system.

---

🧠 Core Idea

One of the first ideas that naturally arises in electricity consumption segmentation is reducing within-segment variance, conceptually related to approaches such as Fisher–Jenks.

However, variance reduction alone was not sufficient for our objective.

We did not want the system to answer only:

«"Where is the variance lower?"»

Instead, the project focuses on:

«"Where does consumer behavior actually change, and is that change meaningful and persistent?"»

Therefore, the segmentation approach has been developed toward an adaptive and behavior-aware methodology.

---

🔄 Adaptive Segmentation

The system uses the previous 30 days to construct a behavioral representation of consumption.

Main pipeline:

Consumption Data
       ↓
Hourly Profile
       ↓
Recent-Data Weighting
       ↓
Weighted Median
       ↓
Noise Reduction
       ↓
Behavior Change Detection
       ↓
Persistence Analysis
       ↓
Segment Boundaries
       ↓
Daily Update

Current parameters:

- 4 contiguous segments
- Minimum segment length: 4 hours
- Maximum segment length: 7 hours
- Historical window: 30 days
- Update frequency: Daily
- Recent-data weighting: "w ∝ 0.97^age"

---

🤖 Forecasting

Current primary model:

Random Forest

Evaluated horizons:

- Day 1
- Day 2
- Day 3

The data is split chronologically:

PAST                                      FUTURE
──────────────────────────────────────────────────►

|--------------- 80% ---------------|--- 20% ---|
              TRAINING                    TEST

This structure is used to evaluate forecasting on future observations while reducing temporal data leakage.

Detailed evaluation methodology and results are provided in the project Word documentation.

---

👥 User Clustering

In addition to temporal segmentation, user behavior is analyzed through clustering.

This provides a foundation for:

- Behavioral user profiles
- Personalized forecasting
- Group-specific models
- Model selection for different behavioral groups

---

📡 IoT Hardware

The project also includes a prototype for real electricity measurement.

Main components:

- ESP32
- CT Clamp
- B101ZMPT
- Wi-Fi

Measured parameters:

RMS Voltage
RMS Current
Real Power
Apparent Power
Power Factor

Measured data can be transmitted through Wi-Fi to the processing and forecasting infrastructure.

---

🏗️ System Architecture

                 ┌─────────────────────┐
                 │   Electricity Data  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │  Data Preprocessing │
                 └──────────┬──────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ Adaptive Behavioral       │
              │ Segmentation              │
              └─────────────┬─────────────┘
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
          ┌──────────────┐     ┌──────────────┐
          │   Clustering │     │   Features   │
          └──────┬───────┘     └──────┬───────┘
                 │                    │
                 └─────────┬──────────┘
                           ▼
                  ┌─────────────────┐
                  │  Random Forest  │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   Forecasting   │
                  └─────────────────┘

---

🎯 Project Goal

The goal is to develop a low-cost, locally developed, and deployable product for electricity monitoring, analysis, and forecasting.

The project is not limited to a theoretical algorithm. The segmentation, forecasting, and real electricity measurement components are being developed as parts of an integrated system.

Research
   ↓
Algorithm
   ↓
Integrated Prototype
   ↓
Low-Cost Product

The development process is intentionally kept close to a practical, usable system.

---

📄 Full Documentation

Detailed technical information is provided in the project Word documentation.

The documentation includes:

- Complete segmentation algorithm
- Adaptive Segmentation methodology
- Segmentation method comparisons
- Model evaluation methodology
- Clustering analysis
- Hardware design
- Circuit and schematic documentation
- Measurement and calibration methodology
- Firmware structure
- Data transmission format
- Product development plan

«📘 For complete technical details, please refer to the project Word documentation.»

---

📚 Dataset

The research component uses:

Smart Meter Energy Consumption Data in London Households

Dataset usage remains subject to the terms and license of the original data source.

---

📺 Demonstration

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

---

⚖️ Copyright & License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

This project is released under the:

Jupiter Code Non-Commercial License

Personal, educational, academic, scientific, and research use is permitted subject to the License terms.

Commercial use requires prior written permission from the Copyright Holder unless separately authorized.

Third-party components, datasets, libraries, models, and dependencies remain subject to their respective licenses.

Full license:

""LICENSE.md"" (LICENSE.md)

---

<div align="center">⚡ Adaptive Intelligence for Electricity Consumption

Research → Algorithm → Prototype → Product

</div>