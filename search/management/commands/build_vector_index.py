"""
Management command для построения векторного индекса поиска
Запускается по расписанию в 3 часа ночи через cron или Celery Beat
"""
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from search.vector_search import build_vector_index, invalidate_cache


class Command(BaseCommand):
    help = 'Построение векторного индекса (FAISS + Sentence Transformers) для семантического поиска услуг'

    def handle(self, *args, **options):
        self.stdout.write('Начало построения векторного индекса...')
        start_time = time.time()
        
        # Очищаем кэш перед перестройкой
        invalidate_cache()
        
        # Строим новый индекс
        index, service_ids, embeddings = build_vector_index()
        
        elapsed_time = time.time() - start_time
        
        if index is not None:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Векторный индекс FAISS успешно построен!\n'
                    f'Обработано услуг: {len(service_ids)}\n'
                    f'Размерность эмбеддингов: {embeddings.shape[1]}\n'
                    f'Время выполнения: {elapsed_time:.2f} сек.'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Не удалось построить индекс: нет активных услуг проверенных компаний'
                )
            )
