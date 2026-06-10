#ifndef CIRCULAR_BUFFER_H
#define CIRCULAR_BUFFER_H

#include <stdint.h>
#include <stdbool.h>
#include "weather_types.h"

/*
 * Circular buffer for on-device flash storage.
 *
 * Capacity is a runtime parameter so the same implementation can be unit
 * tested with a small store without recompiling.
 *
 * Full capacity for production (365 days at 60-second intervals):
 *   365 * 24 * 60 = 525,600 records = ~3.15 MB flash.
 */
#define CIRCULAR_BUFFER_CAPACITY 525600UL

typedef struct {
    StorageRecord *store;    /* pointer to backing array                */
    uint32_t       capacity; /* total slots in store                    */
    uint32_t       head;     /* index of next write position            */
    uint32_t       count;    /* number of valid records currently stored */
} CircularBuffer;

void     cb_init(CircularBuffer *cb, StorageRecord *store, uint32_t capacity);
void     cb_write(CircularBuffer *cb, const StorageRecord *rec);
uint32_t cb_read(const CircularBuffer *cb, StorageRecord *out, uint32_t max);
bool     cb_is_full(const CircularBuffer *cb);
bool     cb_is_empty(const CircularBuffer *cb);
uint32_t cb_count(const CircularBuffer *cb);

#endif /* CIRCULAR_BUFFER_H */
