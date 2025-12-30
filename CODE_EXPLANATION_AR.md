# شرح تفصيلي للكود المضاف (المرحلة 6 - المراقبة)

في هذه الوثيقة، سنشرح بالتفصيل كل سطر كود تمت إضافته لتحقيق المراقبة الشاملة (Observability).

---

## 1. ملف `docker-compose.yml` (البنية التحتية)

أضفنا خدمات جديدة لتشغيل أدوات المراقبة:

```yaml
  # 1. Elasticsearch: قاعدة البيانات التي تخزن السجلات
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:7.17.10
    environment:
      - discovery.type=single-node  # للعمل على جهاز واحد بدون Cluster
    ports:
      - "9200:9200"  # منفذ الوصول للبيانات

  # 2. Logstash: الوسيط الذي يستقبل السجلات من التطبيق ويرسلها لـ Elasticsearch
  logstash:
    image: docker.elastic.co/logstash/logstash:7.17.10
    volumes:
      - ./logstash/pipeline:/usr/share/logstash/pipeline  # ربط ملف الإعدادات
    ports:
      - "5000:5000/tcp"  # المنفذ الذي يرسل له تطبيق بايثون السجلات
    depends_on:
      - elasticsearch

  # 3. Kibana: واجهة المستخدم لعرض السجلات
  kibana:
    image: docker.elastic.co/kibana/kibana:7.17.10
    ports:
      - "5601:5601"  # منفذ المتصفح
    depends_on:
      - elasticsearch

  # 4. Prometheus: نظام جمع المقاييس (Metrics)
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml  # ملف إعدادات المصادر
    ports:
      - "9091:9090"  # غيرنا المنفذ الخارجي لـ 9091 لتجنب التعارض

  # 5. Grafana: واجهة عرض الرسوم البيانية
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
```

---

## 2. ملفات `app.py` (تعديلات بايثون)

تم تعديل كل الخدمات (مثل `order-service`, `api-gateway`) لإضافة التالي:

### أ. المكتبات المستوردة
```python
import logging
from pythonjsonlogger import jsonlogger  # لتحويل السجلات لـ JSON
import logstash  # لإرسال السجلات لـ Logstash مباشرة
from prometheus_flask_exporter import PrometheusMetrics  # لتصدير المقاييس
```

### ب. إعدادات التسجيل (Logging Setup)
```python
# تهيئة الـ Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 1. إعداد الطباعة على الشاشة (Console) بصيغة JSON
logHandler = logging.StreamHandler()
# نستخدم %(asctime)s للوقت بدلاً من timestamp
formatter = jsonlogger.JsonFormatter('%(asctime)s %(level)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# 2. إعداد الإرسال لـ Logstash
# يرسل السجلات عبر TCP للمنفذ 5000 في خدمة logstash
logstash_handler = logstash.TCPLogstashHandler('logstash', 5000, version=1)
logger.addHandler(logstash_handler)
```

### ج. إعداد المقاييس (Metrics)
```python
app = Flask(__name__)
# تفعيل Prometheus وتحديد الرابط /metrics
# هذا يجعل التطبيق يعرض إحصائيات مثل عدد الطلبات ووقت الاستجابة
metrics = PrometheusMetrics(app, path='/metrics')
```

### د. تتبع الطلبات (Correlation ID) - في `api-gateway`
```python
# عند استلام طلب جديد
correlation_id = request.headers.get('X-Correlation-ID') or str(uuid.uuid4())

# عند إرسال الطلب لخدمة أخرى (Proxy)
headers_to_forward['X-Correlation-ID'] = correlation_id

# تسجيل العملية مع المعرف
logger.info(..., extra={'correlation_id': correlation_id})
```

### هـ. استلام التتبع - في باقي الخدمات
```python
@app.before_request
def before_request():
    # استخراج المعرف القادم من الـ Gateway
    g.correlation_id = request.headers.get('X-Correlation-ID')
    
    # تسجيل استلام الطلب مع المعرف
    logger.info(..., extra={'correlation_id': g.correlation_id})
```

---

## 3. ملفات الإعدادات

### أ. `logstash/pipeline/logstash.conf`
يخبر Logstash كيف يعالج البيانات:
```conf
input {
  tcp {
    port => 5000
    codec => json  # البيانات القادمة بصيغة JSON
  }
}
output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]  # أرسلها لقاعدة البيانات
    index => "microservices-logs-%{+YYYY.MM.dd}"  # اسم الفهرس اليومي
  }
}
```

### ب. `prometheus.yml`
يخبر Prometheus من أين يجمع البيانات:
```yaml
scrape_configs:
  - job_name: 'microservices'
    static_configs:
      - targets: 
        - 'api-gateway:8080'
        - 'order-service:5003'
        # ... باقي الخدمات
```
هذا يجعل Prometheus يزور `http://api-gateway:8080/metrics` كل فترة لجمع الأرقام.
 