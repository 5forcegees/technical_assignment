#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "../include/weather_types.h"
#include "../include/circular_buffer.h"

static int passed = 0;
static int failed = 0;

#define CHECK(cond, name) do { \
    if (cond) { printf("  PASS  %s\n", name); passed++; } \
    else       { printf("  FAIL  %s\n", name); failed++; } \
} while(0)

#define TEST_CAP 8

static StorageRecord store[TEST_CAP];
static CircularBuffer buf;

static StorageRecord make_rec(uint32_t ts)
{
    StorageRecord r;
    r.timestamp   = ts;
    r.temperature = (int8_t)(ts % 50);
    r.humidity    = (uint8_t)(ts % 101);
    return r;
}

static void setup(void)
{
    memset(store, 0, sizeof(store));
    cb_init(&buf, store, TEST_CAP);
}

static void test_init_empty(void)
{
    setup();
    CHECK(cb_is_empty(&buf),   "init: buffer is empty");
    CHECK(!cb_is_full(&buf),   "init: buffer not full");
    CHECK(cb_count(&buf) == 0, "init: count == 0");
}

static void test_write_and_count(void)
{
    setup();
    StorageRecord r = make_rec(1);
    cb_write(&buf, &r);
    CHECK(cb_count(&buf) == 1, "write: count == 1");
    CHECK(!cb_is_empty(&buf),  "write: not empty");
    CHECK(!cb_is_full(&buf),   "write: not full after 1");
}

static void test_fill_to_capacity(void)
{
    setup();
    for (uint32_t i = 0; i < TEST_CAP; i++) {
        StorageRecord r = make_rec(i);
        cb_write(&buf, &r);
    }
    CHECK(cb_is_full(&buf),                "fill: is_full");
    CHECK(cb_count(&buf) == TEST_CAP,      "fill: count == capacity");
}

static void test_overwrite_oldest(void)
{
    setup();
    for (uint32_t i = 0; i < TEST_CAP; i++) {
        StorageRecord r = make_rec(i);
        cb_write(&buf, &r);
    }
    StorageRecord newest = make_rec(100);
    cb_write(&buf, &newest);

    CHECK(cb_count(&buf) == TEST_CAP, "overwrite: count stays at capacity");

    StorageRecord out[TEST_CAP];
    uint32_t n = cb_read(&buf, out, TEST_CAP);
    CHECK(n == TEST_CAP,                     "overwrite: read returns capacity records");
    CHECK(out[0].timestamp == 1,             "overwrite: oldest is now timestamp 1");
    CHECK(out[TEST_CAP - 1].timestamp == 100,"overwrite: newest is timestamp 100");
}

static void test_read_order(void)
{
    setup();
    for (uint32_t i = 10; i < 10 + TEST_CAP; i++) {
        StorageRecord r = make_rec(i);
        cb_write(&buf, &r);
    }
    StorageRecord out[TEST_CAP];
    uint32_t n = cb_read(&buf, out, TEST_CAP);
    CHECK(n == TEST_CAP, "order: read returns all records");
    bool ordered = true;
    for (uint32_t i = 1; i < n; i++) {
        if (out[i].timestamp <= out[i-1].timestamp) { ordered = false; break; }
    }
    CHECK(ordered, "order: records returned oldest-first");
}

static void test_partial_read(void)
{
    setup();
    for (uint32_t i = 0; i < 5; i++) {
        StorageRecord r = make_rec(i);
        cb_write(&buf, &r);
    }
    StorageRecord out[2];
    uint32_t n = cb_read(&buf, out, 2);
    CHECK(n == 2,                "partial read: returns requested count");
    CHECK(out[0].timestamp == 0, "partial read: first is oldest");
    CHECK(out[1].timestamp == 1, "partial read: second is next oldest");
}

static void test_wrap_around(void)
{
    setup();
    for (uint32_t i = 0; i < TEST_CAP * 2; i++) {
        StorageRecord r = make_rec(i);
        cb_write(&buf, &r);
    }
    CHECK(cb_count(&buf) == TEST_CAP, "wrap: count == capacity after 2x writes");

    StorageRecord out[TEST_CAP];
    uint32_t n = cb_read(&buf, out, TEST_CAP);
    CHECK(out[0].timestamp == TEST_CAP,             "wrap: oldest is correct");
    CHECK(out[n-1].timestamp == TEST_CAP * 2 - 1,  "wrap: newest is correct");
}

int main(void)
{
    printf("=== circular_buffer tests ===\n");
    test_init_empty();
    test_write_and_count();
    test_fill_to_capacity();
    test_overwrite_oldest();
    test_read_order();
    test_partial_read();
    test_wrap_around();
    printf("\n%d passed, %d failed\n", passed, failed);
    return failed > 0 ? 1 : 0;
}
