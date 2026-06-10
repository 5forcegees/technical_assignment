#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>
#include "../include/weather_types.h"
#include "../include/weather_packet.h"
#include "../include/crc.h"

static int passed = 0;
static int failed = 0;

#define CHECK(cond, name) do { \
    if (cond) { printf("  PASS  %s\n", name); passed++; } \
    else       { printf("  FAIL  %s\n", name); failed++; } \
} while(0)

static void test_serialization_round_trip(void)
{
    WeatherPacket orig = weather_packet_create(0x0042, 1700000000UL, 23, 65);
    uint8_t buf[WEATHER_PACKET_SIZE];
    weather_packet_serialize(&orig, buf);

    WeatherPacket decoded;
    bool ok = weather_packet_deserialize(buf, &decoded);

    CHECK(ok,                                      "round-trip: CRC validates");
    CHECK(decoded.version     == WEATHER_PACKET_VERSION, "round-trip: version");
    CHECK(decoded.device_id   == 0x0042,           "round-trip: device_id");
    CHECK(decoded.timestamp   == 1700000000UL,     "round-trip: timestamp");
    CHECK(decoded.temperature == 23,               "round-trip: temperature");
    CHECK(decoded.humidity    == 65,               "round-trip: humidity");
}

static void test_packet_size(void)
{
    CHECK(WEATHER_PACKET_SIZE == 11, "packet is exactly 11 bytes");
}

static void test_struct_packed(void)
{
    CHECK(sizeof(WeatherPacket) == 11, "WeatherPacket struct size == 11");
    CHECK(sizeof(StorageRecord) == 6,  "StorageRecord struct size == 6");
}

static void test_crc_detects_corruption(void)
{
    WeatherPacket orig = weather_packet_create(1, 1700000001UL, 25, 50);
    uint8_t buf[WEATHER_PACKET_SIZE];
    weather_packet_serialize(&orig, buf);

    buf[4] ^= 0xFF; /* corrupt timestamp byte */

    WeatherPacket decoded;
    bool ok = weather_packet_deserialize(buf, &decoded);
    CHECK(!ok, "CRC rejects corrupted payload");
}

static void test_negative_temperature(void)
{
    WeatherPacket pkt = weather_packet_create(1, 1700000002UL,
                                              -12, 30);
    uint8_t buf[WEATHER_PACKET_SIZE];
    weather_packet_serialize(&pkt, buf);

    WeatherPacket decoded;
    bool ok = weather_packet_deserialize(buf, &decoded);
    CHECK(ok, "negative temp: CRC validates");
    CHECK(decoded.temperature == -12,   "negative temp: value preserved (-12 C)");
}

static void test_boundary_values(void)
{
    /* int8_t max is 127 C — covers agronomic range and LM92 to 127 C */
    WeatherPacket pkt = weather_packet_create(0xFFFF, 0xFFFFFFFFUL,
                                              60,
                                              100);
    uint8_t buf[WEATHER_PACKET_SIZE];
    weather_packet_serialize(&pkt, buf);

    WeatherPacket decoded;
    bool ok = weather_packet_deserialize(buf, &decoded);
    CHECK(ok,                              "boundary: CRC validates");
    CHECK(decoded.device_id == 0xFFFF,     "boundary: max device_id");
    CHECK(decoded.timestamp == 0xFFFFFFFF, "boundary: max timestamp");
    CHECK(decoded.temperature == 60,       "boundary: max temperature (60 C)");
    CHECK(decoded.humidity    == 100,      "boundary: max humidity (100%)");
}

int main(void)
{
    printf("=== weather_packet tests ===\n");
    test_packet_size();
    test_struct_packed();
    test_serialization_round_trip();
    test_crc_detects_corruption();
    test_negative_temperature();
    test_boundary_values();
    printf("\n%d passed, %d failed\n", passed, failed);
    return failed > 0 ? 1 : 0;
}
