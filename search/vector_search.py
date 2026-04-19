"""
Модуль для работы с векторным поиском услуг через TF-IDF + косинусное сходство
Используется как легковесная альтернатива FAISS при ограниченных ресурсах
"""
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from django.conf import settings
from business.models import Service
from .models import ServiceEmbedding


# Глобальные переменные для кэширования
_vectorizer = None
_tfidf_matrix = None
_service_ids = None


def get_service_text(service):
    """Формирует текстовое представление услуги для векторизации"""
    parts = [
        service.name,
        service.description or '',
        service.company.name if service.company else '',
    ]
    # Добавляем название категории и подкатегории если есть
    if service.category:
        parts.append(service.category.name)
    if service.subcategory:
        parts.append(service.subcategory.name)
    
    return ' '.join(filter(None, parts))


def build_vector_index():
    """
    Строит TF-IDF индекс для всех активных услуг.
    Сохраняет данные в базу данных и возвращает матрицу для поиска.
    """
    global _vectorizer, _tfidf_matrix, _service_ids
    
    # Получаем все активные услуги проверенных компаний
    services = Service.objects.select_related('company', 'category', 'subcategory').filter(
        status='active',
        company__is_verified=True
    )
    
    if not services.exists():
        return None, [], None
    
    # Генерируем тексты
    texts = []
    service_id_list = []
    
    for service in services:
        text = get_service_text(service)
        texts.append(text)
        service_id_list.append(service.id)
    
    # Создаем TF-IDF векторизатор
    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),  # Униграммы и биграммы
        min_df=1,
        stop_words=None  # Для русского языка лучше не использовать стандартные стоп-слова
    )
    
    tfidf_matrix = vectorizer.fit_transform(texts)
    
    # Сохраняем векторизатор и данные в базу
    ServiceEmbedding.objects.all().delete()  # Очищаем старые эмбеддинги
    
    # Сохраняем сам векторизатор и матрицу
    vectorizer_data = pickle.dumps(vectorizer)
    matrix_data = pickle.dumps(tfidf_matrix)
    
    # Сохраняем как один большой объект (векторизатор + матрица)
    combined_data = pickle.dumps({
        'vectorizer': vectorizer,
        'tfidf_matrix': tfidf_matrix,
        'service_ids': service_id_list
    })
    
    # Для совместимости сохраняем в первую запись
    if services.exists():
        first_service = services.first()
        embedding_obj = ServiceEmbedding(
            service_id=first_service.id,
            embedding=combined_data
        )
        embedding_obj.save()
    
    # Кэшируем в памяти
    _vectorizer = vectorizer
    _tfidf_matrix = tfidf_matrix
    _service_ids = service_id_list
    
    return vectorizer, service_id_list, tfidf_matrix


def load_vector_index():
    """
    Загружает TF-IDF индекс из базы данных.
    Возвращает векторизатор, матрицу и список ID услуг.
    """
    global _vectorizer, _tfidf_matrix, _service_ids
    
    if _vectorizer is not None and _tfidf_matrix is not None:
        return _vectorizer, _service_ids, _tfidf_matrix
    
    # Получаем сохраненные данные
    embeddings_qs = ServiceEmbedding.objects.all()
    
    if not embeddings_qs.exists():
        return None, [], None
    
    # Берем первую запись с комбинированными данными
    first_embedding = embeddings_qs.first()
    
    try:
        data = pickle.loads(first_embedding.embedding)
        
        if isinstance(data, dict) and 'vectorizer' in data:
            _vectorizer = data['vectorizer']
            _tfidf_matrix = data['tfidf_matrix']
            _service_ids = data['service_ids']
        else:
            # Старый формат - только вектор
            return None, [], None
            
    except Exception as e:
        print(f"Ошибка загрузки индекса: {e}")
        return None, [], None
    
    return _vectorizer, _service_ids, _tfidf_matrix


def search_similar(query, top_k=10):
    """
    Выполняет семантический поиск по запросу.
    Возвращает список ID услуг, отсортированных по релевантности.
    """
    vectorizer, service_ids, tfidf_matrix = load_vector_index()
    
    if vectorizer is None or tfidf_matrix is None or not service_ids:
        return []
    
    # Векторизуем запрос
    try:
        query_vector = vectorizer.transform([query])
    except Exception:
        return []
    
    # Вычисляем косинусное сходство
    similarities = cosine_similarity(query_vector, tfidf_matrix).flatten()
    
    # Получаем топ-k наиболее похожих
    k = min(top_k, len(similarities))
    top_indices = np.argsort(similarities)[::-1][:k]
    
    # Фильтруем только те, у которых similarity > 0
    result_ids = []
    for idx in top_indices:
        if similarities[idx] > 0:
            result_ids.append(service_ids[idx])
    
    return result_ids


def invalidate_cache():
    """Очищает кэш индекса для принудительной перезагрузки"""
    global _vectorizer, _tfidf_matrix, _service_ids
    _vectorizer = None
    _tfidf_matrix = None
    _service_ids = None
