"""
Модуль для работы с векторным поиском услуг через FAISS + Sentence Transformers
Полноценный семантический поиск на основе нейросетевых эмбеддингов
Использует легковесную модель для работы в условиях ограниченной памяти
"""
import pickle
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from django.conf import settings
from business.models import Service
from .models import ServiceEmbedding


# Глобальные переменные для кэширования
_model = None
_index = None
_service_ids = None
_embeddings_map = None  # Маппинг id -> embedding для быстрых вычислений


def get_model():
    """Ленивая загрузка модели Sentence Transformer"""
    global _model
    if _model is None:
        # Используем максимально легковесную мультиязычную модель
        # paraphrase-multilingual-MiniLM-L12-v2 - компактная модель (~470MB)
        # Если не хватает памяти, модель будет загружена с диска при необходимости
        try:
            _model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        except MemoryError:
            raise MemoryError(
                "Недостаточно оперативной памяти для загрузки модели. "
                "Требуется минимум 1-2GB свободной RAM. "
                "Попробуйте увеличить память сервера или использовать TF-IDF альтернативу."
            )
    return _model


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
    Строит FAISS индекс для всех активных услуг используя Sentence Transformers.
    Сохраняет данные в базу данных и возвращает индекс для поиска.
    Использует batch processing для экономии памяти.
    """
    global _model, _index, _service_ids, _embeddings_map
    
    model = get_model()
    
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
    
    # Генерируем эмбеддинги через Sentence Transformer с batch processing
    # Используем небольшой размер батча для экономии памяти
    batch_size = 8
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i+batch_size]
        batch_embeddings = model.encode(batch_texts, convert_to_numpy=True, show_progress_bar=False)
        all_embeddings.append(batch_embeddings)
    
    embeddings = np.vstack(all_embeddings)
    
    # Нормализуем эмбеддинги для косинусного сходства
    faiss.normalize_L2(embeddings)
    
    # Создаем FAISS индекс (Inner Product для нормализованных векторов = косинусное сходство)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings.astype('float32'))
    
    # Сохраняем эмбеддинги и метаданные в базу данных
    ServiceEmbedding.objects.all().delete()  # Очищаем старые эмбеддинги
    
    # Используем bulk_create для эффективного сохранения
    embeddings_to_create = []
    for i, service_id in enumerate(service_id_list):
        embedding_obj = ServiceEmbedding(
            service_id=service_id,
            embedding=pickle.dumps({
                'embedding': embeddings[i],
                'index_position': i
            })
        )
        embeddings_to_create.append(embedding_obj)
    
    if embeddings_to_create:
        ServiceEmbedding.objects.bulk_create(embeddings_to_create)
    
    # Сохраняем сам индекс и маппинг ID для быстрого доступа
    index_data = pickle.dumps({
        'index': index,
        'service_ids': service_id_list,
        'dimension': dimension
    })
    
    # Сохраняем индекс в отдельную запись с фиктивным service_id (используем первый)
    # Но НЕ используем OneToOne связь для этой записи, а создаем специальную запись
    # Для этого временно отключаем проверку уникальности или используем update_or_create
    index_embedding, created = ServiceEmbedding.objects.update_or_create(
        service_id=-1,  # Специальный ID для хранения индекса
        defaults={
            'embedding': index_data
        }
    )
    
    # Кэшируем в памяти
    _model = model
    _index = index
    _service_ids = service_id_list
    _embeddings_map = {sid: embeddings[i] for i, sid in enumerate(service_id_list)}
    
    return index, service_id_list, embeddings


def load_vector_index():
    """
    Загружает FAISS индекс из базы данных.
    Возвращает индекс, список ID услуг и маппинг эмбеддингов.
    """
    global _model, _index, _service_ids, _embeddings_map
    
    if _index is not None and _service_ids is not None:
        return _index, _service_ids, _embeddings_map
    
    # Получаем сохраненные данные
    embeddings_qs = ServiceEmbedding.objects.all()
    
    if not embeddings_qs.exists():
        return None, [], None
    
    # Ищем запись с индексом (содержит ключ 'index')
    index_record = None
    service_records = []
    
    for emb in embeddings_qs:
        try:
            data = pickle.loads(emb.embedding)
            if isinstance(data, dict) and 'index' in data:
                index_record = data
            elif isinstance(data, dict) and 'embedding' in data and 'index_position' in data:
                service_records.append(data)
        except Exception:
            continue
    
    if index_record is None:
        return None, [], None
    
    # Восстанавливаем индекс
    _index = index_record['index']
    _service_ids = index_record['service_ids']
    
    # Строим маппинг эмбеддингов
    _embeddings_map = {}
    for record in service_records:
        _embeddings_map[record['service_id']] = record['embedding']
    
    # Загружаем модель
    _model = get_model()
    
    return _index, _service_ids, _embeddings_map


def search_similar(query, top_k=10):
    """
    Выполняет семантический поиск по запросу используя FAISS.
    Возвращает список ID услуг, отсортированных по релевантности.
    """
    index, service_ids, embeddings_map = load_vector_index()
    
    if index is None or not service_ids:
        return []
    
    model = get_model()
    
    # Генерируем эмбеддинг запроса
    query_embedding = model.encode([query], convert_to_numpy=True)
    faiss.normalize_L2(query_embedding)
    
    # Ищем ближайшие соседи в FAISS
    k = min(top_k, len(service_ids))
    distances, indices = index.search(query_embedding.astype('float32'), k)
    
    # Преобразуем результаты в список ID
    result_ids = []
    for i, idx in enumerate(indices[0]):
        if idx < len(service_ids) and distances[0][i] > 0:  # Только положительные similarity
            result_ids.append(service_ids[idx])
    
    return result_ids


def invalidate_cache():
    """Очищает кэш индекса для принудительной перезагрузки"""
    global _model, _index, _service_ids, _embeddings_map
    _model = None
    _index = None
    _service_ids = None
    _embeddings_map = None
