FROM python:3.12-slim
WORKDIR /app
COPY receipt_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY receipt_service ./receipt_service
CMD ["python", "-m", "receipt_service.main"]
