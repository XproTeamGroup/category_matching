# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Installation
```bash
pip install -r requirements.txt
```

### Running the Application

#### Hierarchical Mode (NEW - Recommended)
```bash
# Basic hierarchical matching
python main_hierarchical.py --reference data/reference_categories.json \
                            --input data/input_categories.json \
                            --output data/output.json

# With debugging and summary
python main_hierarchical.py --reference data/reference_categories.json \
                            --input data/input_categories.json \
                            --output data/output.json \
                            --debug-trees --summary-file data/summary.txt

# Debug mode
python main_hierarchical.py --reference data/reference_categories.json \
                            --input data/input_categories.json \
                            --output data/output.json \
                            --log-level DEBUG
```

#### Legacy Mode (Old System)
```bash
# Standard mode
python main.py --reference data/input/reference_categories.json \
               --input data/input/input_categories.json \
               --output data/output/results.json

# Ultra-optimized mode 
python main.py --reference data/input/reference_categories.json \
               --input data/input/input_categories.json \
               --output data/output/results.json \
               --ultra-optimize --batch-size 20
```

### Testing and Validation
The application does not have automated tests. Validation is done through:
- Manual testing with sample data files
- Performance benchmarking: `--benchmark` flag
- Output validation through result file inspection

## Architecture Overview

This is a **hierarchical category matching system** that uses Claude API to intelligently match product categories with path-based context awareness. The system supports both reference and input files with hierarchical structures and optimizes AI costs through smart pre-filtering.

### NEW: Hierarchical System Components

1. **HierarchicalMatcher** (`src/hierarchical_matcher.py`) - Main orchestrator for hierarchical matching
2. **HierarchicalProcessor** (`src/hierarchical_processor.py`) - Tree parsing and path-aware category management
3. **ClaudeAPIClient** (`src/claude_client.py`) - Enhanced for hierarchical prompts with path context
4. **CategoryNode** - Data structure representing hierarchical category nodes with full path information

### Legacy System Components (Still Available)

1. **OptimizedCategoryMatcher** (`src/optimized_matcher.py`) - Main orchestrator for flat category matching
2. **CategoryProcessor** (`src/processor.py`) - Handles data loading for flat structures
3. **Batch Processors** - Multiple processors for different optimization levels
4. **CacheManager** (`src/cache_manager.py`) - Multi-layer caching
5. **VectorSearch** (`src/vector_search.py`) - TF-IDF vectorization
6. **AdvancedFilter** (`src/advanced_filter.py`) - Multi-level pre-filtering

### NEW: Hierarchical Processing Features

The hierarchical system introduces advanced path-aware matching:

1. **Leaf-Only Processing**: Automatically identifies and processes only final category nodes (leaves)
2. **Path-Based Disambiguation**: Resolves duplicate category names using full path context
3. **Branch Grouping**: Groups input categories by target reference branches for optimal batch processing
4. **Context-Aware Matching**: Uses hierarchical context to disambiguate categories like "Аксессуары" in different branches

### Hierarchical Optimization Features

1. **Exact Path Matching**: Automatically matches categories with identical names without AI (33%+ savings)
2. **Branch-Optimized Batching**: Groups categories by reference branches, reducing context size for AI
3. **Smart Pre-filtering**: Eliminates obvious mismatches before AI processing
4. **Path Context Prompting**: Provides AI with full hierarchical context for accurate disambiguation

### Legacy Processing Modes (Old System)

- **< 200 categories**: Standard mode with simple filtering
- **200-10,000 categories**: Optimized mode with advanced filtering and indexing  
- **> 10,000 categories**: Large data mode with vector search, chunking, and parallelism

## Configuration

Primary configuration in `config/settings.py`:

```python
# Processing
BATCH_SIZE = 25  # Categories per API request
CONFIDENCE_THRESHOLD = 0.7  # Minimum match confidence
LARGE_DATASET_THRESHOLD = 100  # Switch to optimized mode

# Performance  
ENABLE_VECTOR_SEARCH = True
MAX_WORKERS = 4  # Parallel processing threads
MEMORY_LIMIT_MB = 2048  # Cache memory limit

# API
CLAUDE_MODEL = "claude-3-5-haiku-20241022"  # Fast, cost-effective model
```

## Data Format

### Hierarchical Format (NEW - Recommended)
Both reference and input files use the same hierarchical structure:

**Reference categories**:
```json
[
  {"id": "1000", "name": "Мотоциклы", "path": "1000"},
  {"id": "1001", "name": "Спортбайки", "path": "1000>1001"},
  {"id": "1003", "name": "Аксессуары", "path": "1000>1003"},
  {"id": "1004", "name": "Шлемы", "path": "1000>1003>1004"}
]
```

**Input categories**:
```json
[
  {"id": "input_1", "name": "Мотошлемы", "path": "input_moto>input_accessories>input_1"},
  {"id": "input_2", "name": "Перчатки мотоциклетные", "path": "input_moto>input_accessories>input_2"}
]
```

### Legacy Format (Old System)
- **Reference categories**: `[{"id": "123", "name": "Category Name", "path": "parent>child"}]`
- **Input categories**: `[{"name": "Category to Match"}]`

### Hierarchical Output Format (NEW)
```json
{
  "processed_at": "2025-09-09T23:22:41.228646",
  "total_input": 6,
  "total_matched": 6,
  "total_unmatched": 0,
  "matches": [{
    "input_id": "input_1",
    "input_name": "Мотошлемы", 
    "input_path": "input_moto>input_accessories>input_1",
    "input_full_path": "Мотошлемы",
    "match_id": "1004",
    "match_name": "Шлемы",
    "match_path": "1000>1003>1004", 
    "match_full_path": "Мотоциклы > Аксессуары > Шлемы",
    "confidence": 1.0,
    "reasoning": "Точное соответствие по названию и иерархическому пути",
    "method": "ai"
  }],
  "statistics": {
    "exact_matches": 2,
    "ai_matches": 4,
    "api_requests": 2,
    "processing_time": "11.61s"
  }
}
```

### Legacy Output Format
```json
{
  "processed_at": "2025-09-09T10:00:00Z",
  "total_input": 1000,
  "total_matched": 850,
  "matches": [{
    "input_name": "Input Category",
    "match_id": "123", 
    "match_name": "Matched Category",
    "match_path": "parent>child>123",
    "confidence": 0.95,
    "reasoning": "Explanation of match"
  }]
}
```

## Performance Optimization Guidelines

### For Hierarchical System (Recommended)
- Use `main_hierarchical.py` for all new projects with hierarchical data
- System automatically processes only leaf nodes for maximum efficiency
- Expect 30%+ exact matches without AI costs
- Use `--debug-trees` to inspect tree structure and validate data
- Optimal batch size is automatically determined by branch grouping

### For Legacy System  
- Use `--ultra-optimize` for datasets >500 categories
- Increase `--batch-size` to 20-25 for maximum API efficiency  
- Monitor automatic match percentage (should be >40% for good synonym coverage)
- Use `--disable-vector-search` if memory is constrained

### General Guidelines
- Set `CLAUDE_API_KEY` environment variable to avoid costs during development
- Use summary files (`--summary-file`) for quick performance overview
- Monitor API request counts to control costs

## Common Development Patterns

### Adding New Processors
New batch processors should inherit from base patterns and implement:
- `process_batch()` method for handling category batches
- Proper error handling and logging
- Performance metrics recording via `performance_monitor`

### Cache Integration
All heavy operations should use the cache manager:
```python
cache_key = f"operation_{hash(input_data)}"
result = self.cache_manager.get(cache_key)
if result is None:
    result = expensive_operation()
    self.cache_manager.set(cache_key, result)
```

### Logging Standards
Use structured logging with appropriate levels:
- INFO: High-level operations and statistics
- DEBUG: Detailed processing information  
- WARNING: Performance issues or fallback operations
- ERROR: API failures and critical errors

## Environment Setup

Required environment variables:
- `CLAUDE_API_KEY` - Your Anthropic Claude API key

The system automatically creates necessary directories (`cache/`, `data/output/`) and handles graceful shutdown via signal handlers.