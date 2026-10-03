⚡ Smart Electricity Consumption Prediction System

سامانه هوشمند پیش‌بینی مصرف برق

<p align="center">
  <b>Adaptive Behavioral Segmentation • Machine Learning • IoT • Energy Intelligence</b>
</p><p align="center">
  <a href="#-english">English</a> •
  <a href="#-فارسی">فارسی</a>
</p>---

<a name="english"></a>

🇬🇧 English

📌 Overview

Smart Electricity Consumption Prediction System is a research-to-product project developed by Jupiter Code.

The system combines:

- ⚡ Electricity consumption forecasting
- 🧠 Behavior-aware adaptive segmentation
- 👥 User behavior clustering
- 📡 IoT-based energy measurement
- 🤖 Machine learning
- 📊 Time-series analysis
- 🔄 Continuous adaptation to changing consumption behavior

The core idea is simple:

«Electricity consumption is not only a numerical signal — it is a reflection of user behavior.»

Therefore, the system does not rely solely on variance minimization. It attempts to identify meaningful, persistent and recurring behavioral transitions and use them as part of the forecasting pipeline.

---

🎯 Vision

The goal of this project is not to remain only a research idea.

We aim to transform it into a:

«Low-cost, locally developed electricity monitoring and prediction product.»

The long-term pipeline is:

Measure
   ↓
Collect
   ↓
Understand Behavior
   ↓
Adaptive Segmentation
   ↓
Forecast
   ↓
Energy Intelligence

The project therefore focuses on both scientific methodology and practical product development.

---

🧠 Adaptive Behavior-Aware Segmentation

Why not simply minimize variance?

When segmenting a 24-hour electricity consumption profile, one of the first natural ideas is to divide the profile so that the variance inside each segment is minimized.

This is conceptually related to approaches such as Fisher–Jenks natural breaks.

Jenks is useful when the primary objective is statistical partitioning and reducing within-segment dispersion.

However, this was not sufficient for our objective.

We did not want the system to answer only:

«"Where is the variance lower?"»

We wanted it to answer:

«"Where does the user's consumption behavior actually change, and does that change persist?"»

This distinction is fundamental to the proposed approach.

---

Jenks vs. Adaptive Segmentation

Fisher/Jenks

The classical approach focuses primarily on minimizing within-segment dispersion.

Consumption Profile
        ↓
Find statistical breaks
        ↓
Minimize within-segment variance
        ↓
Create segments

Our Adaptive Approach

Our approach incorporates recent behavioral information.

Previous 30 Days
        ↓
Weighted Behavioral Profile
        ↓
Noise Reduction
        ↓
Behavioral Change Analysis
        ↓
Boundary Scoring
        ↓
Structural Constraints
        ↓
4 Adaptive Segments
        ↓
Daily Update

The objective is therefore not simply lower variance, but more meaningful behavioral segmentation for downstream forecasting.

---

🔄 Adaptive Segmentation Pipeline

The current segmentation mechanism uses a rolling historical window of 30 previous days.

Main steps

1. Construct an hourly behavioral profile.
2. Use a weighted median to reduce the effect of abnormal observations.
3. Give more importance to recent days.
4. Smooth the resulting profile.
5. Detect candidate behavioral transitions.
6. Evaluate transition strength and persistence.
7. Apply segment-duration constraints.
8. Produce four contiguous segments.
9. Recalculate the boundaries for each day.

Current structural constraints

- Number of segments: 4
- Minimum segment length: 4 hours
- Maximum segment length: 7 hours
- Historical window: 30 days
- Boundary update: Daily

---

📐 Behavioral Profile

Recent observations receive greater importance using a decay-based weighting scheme:

w ∝ 0.97^age

A weighted median is then used to construct a stable hourly profile.

A centered rolling mean is subsequently applied to reduce short-term noise.

This allows the system to react to recent behavioral changes without allowing a single abnormal observation to dominate the segmentation.

---

📊 Evaluation Dataset

The benchmark uses real-world Smart Meter London electricity consumption data.

Dataset

Property| Value
Dataset| Smart Meter London
Households| 1,000
Period| December 2012 – December 2013
Evaluation| Temporal split
Training| 80%
Testing| 20%
Forecast Horizons| Day 1, Day 2, Day 3

The final 20% of the chronological timeline is reserved exclusively for testing.

---

⏱️ Training / Testing Strategy

The project uses a temporal 80/20 split.

PAST                                                     FUTURE
──────────────────────────────────────────────────────────────►

|---------------------- 80% ----------------------|---- 20% ----|
                     TRAINING                         TEST

This is intentionally not a random split.

For a forecasting problem, the model should learn from the past and be evaluated on unseen future observations.

Therefore:

«80% chronological training + 20% chronological testing»

is used for the benchmark.

---

🤖 Forecasting

The current benchmark evaluates three forecasting horizons:

- Day 1
- Day 2
- Day 3

A direct forecasting strategy is used.

The primary forecasting model in the current benchmark is:

Random Forest

Random Forest was selected as the main forecasting model based on the evaluated model behavior.

The adaptive segmentation component remains important because it provides an explicit behavioral representation and allows the system to analyze how changing consumption structures affect forecasting.

---

📈 Benchmark Results

The benchmark compares Adaptive Segmentation with Jenks-based Segmentation using a global Random Forest model.

Horizon| Adaptive WAPE| Jenks WAPE| Adaptive R²| Jenks R²| Naive WAPE
Day 1| 18.31%| 18.34%| 0.856| 0.857| 25.28%
Day 2| 20.28%| 20.26%| 0.782| 0.774| 25.31%
Day 3| 21.36%| 21.36%| 0.605| 0.692| 25.42%

Interpretation

The benchmark shows that the adaptive and Jenks approaches can achieve very similar WAPE values across the evaluated horizons.

The purpose of the proposed segmentation is therefore not to claim universal superiority on every metric.

Instead, the research investigates whether behavior-aware adaptive segmentation can maintain competitive forecasting performance while providing a more dynamic representation of user behavior.

---

👥 User Behavior Clustering

The project also investigates behavioral differences between users.

Reported clustering results include:

- 948 clustered devices
- 52 outlier devices
- 2 main behavioral clusters

The clusters represent groups with different levels of consumption regularity and variability.

This component provides a foundation for future:

- User-specific models
- Personalized forecasting
- Behavioral profiling
- Model selection

---

🔬 Clustering and Forecasting

The effect of clustering depends on the forecasting algorithm.

Reported WAPE improvement for clustered models compared with the global model:

Model| Day 1| Day 2| Day 3
Ridge| +79.8%| +66.0%| +31.2%
Random Forest| −1.1%| −1.2%| −0.8%

The benchmark indicates that clustering can have a substantially different effect depending on the model architecture.

Ridge benefits more strongly from behavioral specialization, while Random Forest already captures a significant amount of user heterogeneity through nonlinear modeling.

---

🏗️ System Architecture

"System Architecture" (docs/architecture.png)

The complete pipeline is designed around:

                 ┌──────────────────────┐
                 │   Electricity Data   │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │  Data Preprocessing  │
                 └──────────┬───────────┘
                            │
                            ▼
              ┌────────────────────────────┐
              │ Adaptive Behavioral        │
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

The project is not limited to software.

A low-cost electricity monitoring prototype is also being developed.

Main components

- ESP32
- CT Clamp
- B101ZMPT voltage sensor
- Wi-Fi communication

The hardware measures:

- RMS voltage
- RMS current
- Real power
- Apparent power
- Power factor

---

⚡ Why Measure Voltage?

The initial prototype relied on an approximately fixed 230 V assumption.

However, actual grid voltage can vary.

The updated prototype therefore measures both voltage and current.

This enables calculation of:

Vrms
Irms
Real Power (W)
Apparent Power (VA)
Power Factor

This makes the physical measurement layer more representative of actual electrical conditions.

---

📡 Hardware Data Flow

             Electricity
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
   CT Current         B101ZMPT Voltage
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

The current prototype transmits measurement data approximately every 10 seconds using JSON.

Example:

{
  "current_A": 2.145,
  "voltage_V": 228.4,
  "power_W": 478.2,
  "apparent_power_VA": 490.1,
  "power_factor": 0.976
}

---

🎯 Research → Prototype → Product

The project follows a clear development direction:

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
   Low-Cost Hardware
           │
           ▼
        PRODUCT

The ultimate objective is to develop a locally designed and low-cost energy intelligence platform.

The intended product can eventually combine:

- Real-time electricity measurement
- Behavioral analysis
- Adaptive segmentation
- Consumption forecasting
- User profiling
- Energy management

---

🛣️ Roadmap

Forecasting

- [ ] Improve Day-1 forecasting
- [ ] Develop specialized Day-2 and Day-3 models
- [ ] Evaluate additional forecasting algorithms
- [ ] Compare direct and horizon-specific forecasting

Adaptive Segmentation

- [ ] Improve behavioral transition detection
- [ ] Investigate stronger persistence measures
- [ ] Evaluate seasonal behavior
- [ ] Study adaptive segment counts

Clustering

- [ ] Evaluate additional clustering methods
- [ ] Improve volatile-user detection
- [ ] Investigate specialized models for behavioral groups

Hardware

- [ ] Improve calibration
- [ ] Validate measurements against reference instruments
- [ ] Improve reliability
- [ ] Develop a practical enclosure
- [ ] Optimize communication and deployment cost

Product

- [ ] Integrate hardware and forecasting pipeline
- [ ] Develop monitoring dashboard
- [ ] Build local analytics infrastructure
- [ ] Field-test the system
- [ ] Move toward a deployable local product

---

⚠️ Current Limitations

The system is still under active development.

Current limitations include:

- Forecasting difficulty varies between users.
- Highly volatile consumption remains challenging.
- Day-2 and Day-3 forecasting require further improvement.
- Clustering does not provide the same benefit for every forecasting algorithm.
- Hardware calibration requires careful validation.
- The benchmark dataset does not represent every possible household.

These limitations are treated as part of the research and product-development roadmap.

---

🌱 Project Philosophy

«Do not optimize only what is easy to measure. Model what actually matters.»

Variance is useful.

But variance alone does not necessarily describe user behavior.

Our approach therefore combines:

Statistics + Behavior + Adaptation + Machine Learning + Real Measurement

to move toward a practical electricity intelligence system.

---

📚 Dataset

The project uses the:

Smart Meter Energy Consumption Data in London Households

Dataset.

The dataset is used for research and benchmarking according to its applicable terms.

---

📺 Demonstration

Project demonstrations and development updates:

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

---

📜 Citation & Attribution

If substantial portions of this project are used in academic work, research, demonstrations, competitions, publications, or derivative projects, please provide appropriate attribution:

«Smart Electricity Consumption Prediction System
Jupiter Code / Mohammad Mahdi Vafri»

---

⚖️ Copyright & License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

This project is released under:

Jupiter Code Non-Commercial License v1.1

The covered original materials may be used for personal, educational, academic, scientific, research, and other permitted non-commercial purposes, subject to the terms of the license.

Commercial Use

Commercial use requires prior written permission from the Copyright Holder, unless separately authorized under a commercial license.

This includes, but is not limited to:

- Commercial products
- Paid services
- Commercial SaaS deployments
- Commercial redistribution
- Commercial licensing
- Incorporation into commercial systems

Third-party libraries, datasets, pretrained models, APIs and other external components remain subject to their respective licenses.

For the complete terms, see:

""LICENSE.md"" (LICENSE.md)

---

👨‍💻 Author

Mohammad Mahdi Vafri

Jupiter Code

Smart Electricity Consumption Prediction System

© 2026 Jupiter Code / Mohammad Mahdi Vafri

---

<a name="فارسی"></a>

🇮🇷 فارسی

📌 معرفی

سامانه هوشمند پیش‌بینی مصرف برق یک پروژه پژوهشی و محصول‌محور است که توسط Jupiter Code توسعه داده می‌شود.

این سامانه ترکیبی از موارد زیر است:

- ⚡ پیش‌بینی مصرف برق
- 🧠 سگمنت‌بندی تطبیقی مبتنی بر رفتار
- 👥 خوشه‌بندی رفتار کاربران
- 📡 اندازه‌گیری برق مبتنی بر IoT
- 🤖 یادگیری ماشین
- 📊 تحلیل سری زمانی
- 🔄 سازگاری با تغییرات رفتار مصرف

ایده اصلی پروژه این است:

«مصرف برق فقط یک سیگنال عددی نیست؛ بلکه بازتابی از رفتار مصرف‌کننده است.»

بنابراین هدف ما صرفاً کاهش واریانس درون سگمنت‌ها نیست، بلکه تلاش می‌کنیم تغییرات معنادار، پایدار و تکرارشونده در رفتار مصرف را شناسایی کنیم.

---

🎯 چشم‌انداز

هدف این پروژه این نیست که صرفاً به عنوان یک ایده پژوهشی باقی بماند.

هدف ما تبدیل آن به یک:

«محصول بومی، کم‌هزینه و قابل توسعه برای پایش و پیش‌بینی مصرف برق»

است.

مسیر کلی:

اندازه‌گیری
    ↓
جمع‌آوری داده
    ↓
درک رفتار مصرف
    ↓
سگمنت‌بندی تطبیقی
    ↓
پیش‌بینی
    ↓
هوش انرژی

بنابراین پروژه همزمان روی روش علمی و توسعه محصول واقعی تمرکز دارد.

---

🧠 سگمنت‌بندی تطبیقی مبتنی بر رفتار

چرا فقط کاهش واریانس کافی نیست؟

هنگام سگمنت‌بندی یک پروفایل ۲۴ ساعته مصرف برق، یکی از اولین ایده‌ها کاهش واریانس درون سگمنت‌هاست.

این ایده از نظر مفهومی به روش‌هایی مانند Fisher–Jenks نزدیک است.

روش Jenks برای تقسیم آماری داده‌ها و کاهش پراکندگی درون سگمنت‌ها مفید است.

اما این چیزی نبود که ما می‌خواستیم.

ما نمی‌خواستیم سامانه فقط به این سؤال پاسخ دهد:

««کجا واریانس کمتر است؟»»

بلکه می‌خواستیم به این سؤال پاسخ دهد:

««رفتار واقعی کاربر کجا تغییر می‌کند و آیا این تغییر پایدار و تکرارشونده است؟»»

به همین دلیل روش سگمنت‌بندی را از یک رویکرد صرفاً مبتنی بر واریانس به سمت یک رویکرد تطبیقی و مبتنی بر رفتار توسعه دادیم.

---

🔄 فرایند سگمنت‌بندی تطبیقی

سامانه از ۳۰ روز گذشته برای ساخت نمایی از رفتار اخیر کاربر استفاده می‌کند.

مراحل اصلی:

1. ساخت پروفایل ساعتی رفتار.
2. استفاده از میانه وزندار برای کاهش اثر داده‌های غیرعادی.
3. اهمیت بیشتر دادن به روزهای اخیر.
4. هموارسازی پروفایل.
5. شناسایی تغییرات احتمالی رفتار.
6. بررسی شدت و پایداری تغییر.
7. اعمال قیود طول سگمنت.
8. ایجاد چهار سگمنت پیوسته.
9. محاسبه مجدد مرزها برای هر روز.

قیود فعلی

- تعداد سگمنت: ۴
- حداقل طول: ۴ ساعت
- حداکثر طول: ۷ ساعت
- پنجره تاریخی: ۳۰ روز
- به‌روزرسانی مرزها: روزانه

---

📐 پروفایل رفتاری

برای روزهای اخیر وزن بیشتری در نظر گرفته می‌شود:

w ∝ 0.97^age

ابتدا با استفاده از میانه وزندار یک پروفایل پایدار ساعتی ایجاد می‌شود.

سپس برای کاهش نویز کوتاه‌مدت، هموارسازی انجام می‌شود.

این کار اجازه می‌دهد سامانه نسبت به تغییرات جدید رفتار واکنش نشان دهد، بدون اینکه یک روز غیرعادی به تنهایی ساختار سگمنت‌ها را تغییر دهد.

---

📊 داده ارزیابی

برای بنچمارک از داده واقعی Smart Meter London استفاده شده است.

ویژگی| مقدار
داده| Smart Meter London
خانوار| ۱۰۰۰
بازه| دسامبر ۲۰۱۲ تا دسامبر ۲۰۱۳
روش ارزیابی| تقسیم زمانی
آموزش| ۸۰٪
آزمون| ۲۰٪
افق پیش‌بینی| روز ۱، ۲ و ۳

۲۰٪ پایانی داده‌های زمانی به‌صورت کامل برای آزمون کنار گذاشته شده است.

---

⏱️ نسبت آموزش و آزمون

داده‌ها به شکل ۸۰٪ آموزش و ۲۰٪ آزمون زمانی تقسیم شده‌اند.

گذشته                                                   آینده
──────────────────────────────────────────────────────────────►

|---------------------- ۸۰٪ ----------------------|---- ۲۰٪ ----|
                    آموزش                              آزمون

این تقسیم تصادفی نیست.

مدل ابتدا روی بخش گذشته آموزش می‌بیند و سپس روی داده‌های آینده‌ای که در زمان آموزش مشاهده نکرده است ارزیابی می‌شود.

این نوع تقسیم برای مسئله پیش‌بینی مصرف برق مناسب است.

---

🤖 پیش‌بینی

سامانه سه افق پیش‌بینی را بررسی می‌کند:

- روز اول
- روز دوم
- روز سوم

مدل اصلی فعلی:

Random Forest

بر اساس بنچمارک انجام‌شده، Random Forest به عنوان مدل اصلی انتخاب شده است.

با این حال، سگمنت‌بندی تطبیقی همچنان بخش مهمی از معماری است، زیرا یک نمایش صریح از رفتار مصرف‌کننده ایجاد می‌کند.

---

📈 نتایج بنچمارک

مقایسه سگمنت‌بندی تطبیقی با روش Jenks:

افق| WAPE تطبیقی| WAPE Jenks| R² تطبیقی| R² Jenks| WAPE ساده
روز ۱| 18.31%| 18.34%| 0.856| 0.857| 25.28%
روز ۲| 20.28%| 20.26%| 0.782| 0.774| 25.31%
روز ۳| 21.36%| 21.36%| 0.605| 0.692| 25.42%

نتایج نشان می‌دهند که Adaptive و Jenks از نظر WAPE در افق‌های بررسی‌شده عملکرد بسیار نزدیکی دارند.

بنابراین هدف پروژه ادعای برتری مطلق در تمام معیارها نیست.

هدف این است که بررسی کنیم آیا سگمنت‌بندی تطبیقی مبتنی بر رفتار می‌تواند ضمن حفظ عملکرد رقابتی، نمایش پویاتر و معنادارتری از رفتار مصرف‌کننده ایجاد کند یا خیر.

---

👥 خوشه‌بندی رفتار کاربران

در کنار سگمنت‌بندی روزانه، رفتار کاربران نیز بررسی شده است.

نتایج گزارش‌شده:

- ۹۴۸ دستگاه خوشه‌بندی‌شده
- ۵۲ دستگاه پرت
- ۲ خوشه اصلی

این بخش می‌تواند در آینده برای موارد زیر استفاده شود:

- مدل‌های اختصاصی کاربران
- پیش‌بینی شخصی‌سازی‌شده
- پروفایل رفتاری
- انتخاب مدل مناسب برای هر گروه

---

🔬 تأثیر خوشه‌بندی بر پیش‌بینی

اثر خوشه‌بندی به مدل پیش‌بینی وابسته است.

بهبود گزارش‌شده WAPE:

مدل| روز ۱| روز ۲| روز ۳
Ridge| +79.8%| +66.0%| +31.2%
Random Forest| −1.1%| −1.2%| −0.8%

نتایج نشان می‌دهند که خوشه‌بندی برای همه مدل‌ها اثر یکسانی ندارد.

Ridge از تخصصی‌سازی رفتاری بیشتر بهره می‌برد، در حالی که Random Forest بخش زیادی از تفاوت کاربران را از طریق ساختار غیرخطی خود مدل می‌کند.

---

🏗️ معماری سامانه

"معماری سامانه" (docs/architecture.png)

معماری کلی:

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

پروژه فقط نرم‌افزاری نیست.

یک نمونه اولیه برای اندازه‌گیری مصرف برق نیز توسعه داده شده است.

قطعات اصلی

- ESP32
- CT Clamp
- B101ZMPT
- ارتباط Wi-Fi

پارامترهای اندازه‌گیری:

- RMS Voltage
- RMS Current
- Real Power
- Apparent Power
- Power Factor

---

⚡ چرا اندازه‌گیری ولتاژ؟

در نمونه اولیه، ولتاژ تقریباً ۲۳۰ ولت ثابت فرض می‌شد.

اما ولتاژ واقعی شبکه می‌تواند تغییر کند.

در نسخه جدید، ولتاژ و جریان به صورت همزمان اندازه‌گیری می‌شوند.

در نتیجه موارد زیر محاسبه می‌شوند:

Vrms
Irms
توان واقعی (W)
توان ظاهری (VA)
ضریب توان

این تغییر باعث می‌شود اندازه‌گیری توان به شرایط واقعی شبکه نزدیک‌تر شود.

---

📡 مسیر داده سخت‌افزار

              شبکه برق
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
      CT Clamp          B101ZMPT
       جریان              ولتاژ
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
          هوش مصنوعی / پیش‌بینی

نمونه داده:

{
  "current_A": 2.145,
  "voltage_V": 228.4,
  "power_W": 478.2,
  "apparent_power_VA": 490.1,
  "power_factor": 0.976
}

---

🎯 مسیر پروژه: پژوهش → نمونه اولیه → محصول

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

هدف نهایی، ایجاد یک سامانه بومی هوش انرژی است که بتواند اندازه‌گیری واقعی برق را با تحلیل رفتار و پیش‌بینی مصرف ترکیب کند.

---

🛣️ نقشه راه

پیش‌بینی

- [ ] بهبود پیش‌بینی روز اول
- [ ] توسعه مدل اختصاصی برای روز دوم و سوم
- [ ] بررسی الگوریتم‌های مختلف
- [ ] مقایسه پیش‌بینی مستقیم و افق‌محور

سگمنت‌بندی تطبیقی

- [ ] بهبود تشخیص تغییرات رفتاری
- [ ] بررسی معیارهای بهتر پایداری
- [ ] بررسی رفتار فصلی
- [ ] بررسی تعداد سگمنت‌های تطبیقی

خوشه‌بندی

- [ ] بررسی روش‌های بیشتر
- [ ] تشخیص بهتر کاربران پرنوسان
- [ ] توسعه مدل‌های اختصاصی گروه‌های رفتاری

سخت‌افزار

- [ ] بهبود کالیبراسیون
- [ ] اعتبارسنجی با ابزارهای مرجع
- [ ] افزایش قابلیت اطمینان
- [ ] طراحی بدنه مناسب
- [ ] کاهش هزینه

محصول

- [ ] اتصال کامل سخت‌افزار و مدل پیش‌بینی
- [ ] توسعه داشبورد
- [ ] توسعه زیرساخت تحلیل محلی
- [ ] تست میدانی
- [ ] حرکت به سمت محصول قابل عرضه

---

⚠️ محدودیت‌های فعلی

پروژه همچنان در حال توسعه است.

محدودیت‌های فعلی:

- دشواری پیش‌بینی بین کاربران متفاوت است.
- کاربران بسیار پرنوسان همچنان چالش‌برانگیز هستند.
- پیش‌بینی روز دوم و سوم نیاز به بهبود دارد.
- خوشه‌بندی برای تمام مدل‌ها اثر یکسانی ندارد.
- کالیبراسیون سخت‌افزار نیازمند اعتبارسنجی دقیق است.
- داده بنچمارک تمام الگوهای مصرف خانوار را پوشش نمی‌دهد.

این موارد بخشی از مسیر توسعه آینده پروژه هستند.

---

🌱 فلسفه پروژه

«فقط چیزی را که اندازه‌گیری آن آسان است بهینه نکن؛ چیزی را مدل کن که واقعاً اهمیت دارد.»

واریانس یک معیار مفید است.

اما واریانس به‌تنهایی لزوماً رفتار کاربر را توصیف نمی‌کند.

به همین دلیل پروژه ترکیبی از:

آمار + رفتار + سازگاری + یادگیری ماشین + اندازه‌گیری واقعی

را دنبال می‌کند.

---

📚 داده

داده مورد استفاده در بنچمارک:

Smart Meter Energy Consumption Data in London Households

است.

استفاده از داده تابع شرایط و مجوز مربوط به منبع داده است.

---

📺 نمایش پروژه

Jupiter Code — Aparat

https://www.aparat.com/jupyter_code

---

📜 استناد و انتساب

در صورت استفاده قابل‌توجه از این پروژه در پژوهش، مقاله، ارائه، مسابقه، پروژه دانشگاهی یا پروژه مشتق‌شده، لطفاً به شکل زیر به پروژه اشاره کنید:

«Smart Electricity Consumption Prediction System
Jupiter Code / Mohammad Mahdi Vafri»

---

⚖️ Copyright / License

Copyright © 2026 Jupiter Code / Mohammad Mahdi Vafri

این پروژه تحت مجوز:

Jupiter Code Non-Commercial License v1.1

منتشر شده است.

استفاده شخصی، آموزشی، دانشگاهی، علمی، پژوهشی و سایر استفاده‌های غیرتجاری مجاز، مطابق شرایط مجوز، مجاز است.

استفاده تجاری

استفاده تجاری نیازمند اجازه کتبی صاحب حق است؛ مگر اینکه تحت یک مجوز تجاری جداگانه اجازه داده شده باشد.

این موارد شامل، اما محدود به این موارد نیست:

- محصولات تجاری
- خدمات پولی
- SaaS تجاری
- توزیع تجاری
- صدور مجوز تجاری
- استفاده در سامانه‌های تجاری

کتابخانه‌ها، داده‌ها، مدل‌های ازپیش‌آموزش‌دیده و سایر اجزای شخص ثالث تابع مجوزهای خود هستند.

شرایط کامل در فایل زیر قرار دارد:

""LICENSE.md"" (LICENSE.md)

---

👨‍💻 توسعه‌دهنده

Mohammad Mahdi Vafri

Jupiter Code

Smart Electricity Consumption Prediction System

© 2026 Jupiter Code / Mohammad Mahdi Vafri

---

<p align="center">
  <b>Research → Prototype → Product</b>
  <br>
  Adaptive Intelligence for Electricity Consumption
</p>

