-- Migration: Enable pgvector extension for embedding storage and similarity search
-- Date: 2025-11-24
-- Description: Adds pgvector extension to support vector embeddings for bullet matching

-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify extension is available
-- You can check with: SELECT * FROM pg_extension WHERE extname = 'vector';
