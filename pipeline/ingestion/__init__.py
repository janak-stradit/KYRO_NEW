"""ingestion/__init__.py"""
from pipeline.ingestion.ingestor import ingest, from_dict_list, chunked_reader
__all__ = ["ingest", "from_dict_list", "chunked_reader"]
