#include "circular_buffer.h"

void cb_init(CircularBuffer *cb, StorageRecord *store, uint32_t capacity)
{
    cb->store    = store;
    cb->capacity = capacity;
    cb->head     = 0;
    cb->count    = 0;
}

void cb_write(CircularBuffer *cb, const StorageRecord *rec)
{
    cb->store[cb->head] = *rec;
    cb->head = (cb->head + 1) % cb->capacity;
    if (cb->count < cb->capacity)
        cb->count++;
}

uint32_t cb_read(const CircularBuffer *cb, StorageRecord *out, uint32_t max)
{
    uint32_t n = (cb->count < max) ? cb->count : max;
    uint32_t start = (cb->head + cb->capacity - cb->count) % cb->capacity;
    for (uint32_t i = 0; i < n; i++)
        out[i] = cb->store[(start + i) % cb->capacity];
    return n;
}

bool cb_is_full(const CircularBuffer *cb)  { return cb->count == cb->capacity; }
bool cb_is_empty(const CircularBuffer *cb) { return cb->count == 0; }
uint32_t cb_count(const CircularBuffer *cb) { return cb->count; }
