# تقرير المرحلة 7: تنسيق الحاويات باستخدام Kubernetes (Kubernetes Orchestration)

## 1. مقدمة
في هذه المرحلة، قمنا بالانتقال من استخدام **Docker Compose** (المناسب لبيئة التطوير) إلى **Kubernetes** (المعيار الذهبي لبيئة الإنتاج). الهدف هو تحقيق:
*   **الإصلاح الذاتي (Self-Healing)**: إعادة تشغيل الحاويات المتعطلة تلقائياً.
*   **التوسع التلقائي (Auto-Scaling)**: زيادة عدد النسخ (Pods) بناءً على الضغط.
*   **تحديث بدون توقف (Zero-Downtime Deployment)**: تحديث التطبيق دون قطع الخدمة عن المستخدمين.

---

## 2. الملفات التي تم إنشاؤها (شرح تفصيلي)

لقد قمت بإنشاء مجلد `k8s/` يحتوي على جميع ملفات التكوين (Manifests) اللازمة:

### أ. الهيكل التنظيمي (`k8s/namespaces.yaml`)
*   **الغرض**: تقسيم العنقود (Cluster) إلى بيئات منطقية.
*   **التفاصيل**:
    *   `ecommerce-infra`: مخصص للبنية التحتية مثل قواعد البيانات و RabbitMQ.
    *   `ecommerce-services`: مخصص للخدمات المصغرة (Microservices) الخاصة بالتطبيق.

### ب. الإعدادات والسرية (`k8s/base/`)
1.  **`configmaps.yaml`**:
    *   يخزن المتغيرات البيئية العامة مثل `FLASK_ENV` وعناوين الخدمات (`ORDER_SERVICE_URL`، إلخ).
    *   يسمح بتغيير الإعدادات دون إعادة بناء الصور.
2.  **`secrets.yaml`**:
    *   يخزن البيانات الحساسة مثل `SECRET_KEY` بشكل مشفر (Base64).

### ج. البنية التحتية (`k8s/infra/rabbitmq.yaml`)
*   **StatefulSet**: تم استخدامه بدلاً من Deployment لأن RabbitMQ يحتاج إلى تخزين دائم وحالة ثابتة.
*   **PersistentVolumeClaim (PVC)**: لضمان عدم ضياع الرسائل في حال إعادة تشغيل الحاوية.
*   **Headless Service**: لتمكين الاتصال الشبكي المستقر داخل العنقود.

### د. الخدمات المصغرة (`k8s/services/*.yaml`)
لكل خدمة (مثل `order-service`، `payment-service`...) قمنا بإنشاء ملف يحتوي على:
1.  **Deployment**:
    *   `replicas: 2`: لضمان وجود نسختين تعملان دائماً (High Availability).
    *   `livenessProbe`: يفحص هل التطبيق "حي"؟ إذا لا، يقوم Kubernetes بإعادة تشغيله.
    *   `readinessProbe`: يفحص هل التطبيق "جاهز" لاستقبال الطلبات؟ إذا لا، يمنع توجيه المرور إليه مؤقتاً.
2.  **Service (ClusterIP)**:
    *   يوفر عنوان IP داخلي ثابت وموزع حمل (Load Balancer) لتوزيع الطلبات بين النسخ.

### هـ. التوجيه (`k8s/services/ingress.yaml`)
*   **الغرض**: استبدال حاوية NGINX اليدوية بـ **Ingress Controller** الذي يديره Kubernetes.
*   **الوظيفة**: يوجه الطلبات القادمة من الخارج إلى الخدمة المناسبة بناءً على المسار:
    *   `/api/orders` -> `order-service`
    *   `/api/customers` -> `customer-service`
    *   وهكذا...

### و. التوسع التلقائي (`k8s/services/hpa.yaml`)
*   **Horizontal Pod Autoscaler (HPA)**:
    *   يراقب استهلاك المعالج (CPU).
    *   إذا تجاوز الاستهلاك **70%**، يقوم بزيادة عدد النسخ تلقائياً (حتى 10 نسخ).
    *   إذا قل الضغط، يقلل العدد (حتى نسختين).

---

## 3. كيفية التشغيل (بعد تثبيت Minikube)

بمجرد تثبيت الأدوات (`kubectl` و `minikube`)، يمكنك تشغيل النظام بالأوامر التالية:

1.  **بدء العنقود وتفعيل الإضافات**:
    ```bash
    minikube start
    minikube addons enable ingress  # لتفعيل التوجيه
    minikube addons enable metrics-server # لتفعيل التوسع التلقائي
    ```

2.  **تطبيق الملفات**:
    ```bash
    # 1. إنشاء الـ Namespaces
    kubectl apply -f k8s/namespaces.yaml

    # 2. تطبيق الإعدادات
    kubectl apply -f k8s/base/

    # 3. تشغيل البنية التحتية (RabbitMQ)
    kubectl apply -f k8s/infra/

    # 4. تشغيل الخدمات والتوجيه
    kubectl apply -f k8s/services/
    ```

3.  **التحقق من العمل**:
    ```bash
    # عرض جميع الـ Pods
    kubectl get pods -n ecommerce-services

    # عرض حالة التوجيه (Ingress)
    kubectl get ingress -n ecommerce-services
    ```
