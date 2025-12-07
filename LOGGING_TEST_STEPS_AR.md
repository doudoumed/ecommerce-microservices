# خطوات اختبار السجلات الهيكلية (Testing Steps)

اتبع هذه الخطوات للتأكد من أن نظام التسجيل الجديد يعمل بشكل صحيح.

## الخطوة 1: إعادة بناء الخدمات (Rebuild)
بما أننا أضفنا مكتبة جديدة (`python-json-logger`)، يجب إعادة بناء الحاويات لتثبيتها.
افتح التيرمينال ونفذ الأمر التالي:

```bash
sudo docker compose up --build -d
```
*انتظر حتى تعمل جميع الخدمات (تأكد باستخدام `sudo docker ps`).*

## الخطوة 2: إرسال طلب اختبار (Generate Traffic)
```bash
curl -X GET http://localhost:8080/health
```
Test Login 
```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "ahmed@example.com", "password": "password123"}'
```

## الخطوة 3: فحص سجلات API Gateway
تحقق من سجلات البوابة للتأكد من أنها بتنسيق JSON وتحتوي على `correlation_id`.

```bash
sudo docker compose logs --tail=10 api-gateway
```
**النتيجة المتوقعة:**
يجب أن ترى مخرجات تشبه هذا (لاحظ تنسيق JSON):
```json
{"timestamp": "...", "level": "INFO", "message": "Incoming request: GET /health", "client_ip": "...", "correlation_id": "..."}
```

## الخطوة 4: فحص تتبع الطلب (Tracing)
لنتأكد من أن `correlation_id` ينتقل بين الخدمات. سنقوم بإنشاء طلب يمر عبر `order-service` و `inventory-service`.

1. **إرسال طلب إنشاء طلب (Order):**
   (استخدم التوكن الخاص بالعميل الذي لديك من الاختبارات السابقة)
   ```bash
   # مثال مبسط (تأكد من وضع التوكن الصحيح)
   curl -X POST http://localhost:8080/api/orders \
     -H "Authorization: Bearer $CUSTOMER_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"product_id": 1, "quantity": 1}'
   ```

2. **فحص سجلات Order Service:**
   ```bash
   sudo docker compose logs --tail=20 order-service
   ```
   ابحث عن `correlation_id`.

3. **فحص سجلات Inventory Service:**
   ```bash
   sudo docker compose logs --tail=20 inventory-service
   ```
   **هام:** يجب أن تجد **نفس** الـ `correlation_id` الذي رأيته في `order-service`. هذا يثبت أن التتبع يعمل بنجاح!
