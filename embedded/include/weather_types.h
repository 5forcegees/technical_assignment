#ifndef WEATHER_TYPES_H
#define WEATHER_TYPES_H

#include <stdint.h>

/*
 * WeatherPacket — MQTT transmission unit (11 bytes, packed)
 *
 * temperature: signed integer, whole degrees C  (e.g. 23 = 23 C)
 * humidity:    unsigned integer, whole percent RH (e.g. 65 = 65%)
 *
 * LM92 accuracy: ±0.33 C typical. HDC3020 accuracy: ±1.5% RH typical.
 * Sub-degree / sub-percent encoding is not justified by sensor precision.
 * int8_t covers -128..+127 C — sufficient for the agronomic range (-40..+60 C)
 * and the full LM92 operating range up to +127 C.
 */
typedef struct __attribute__((packed)) {
    uint8_t  version;      /* protocol version — increment on breaking changes */
    uint16_t device_id;    /* unique station identifier                         */
    uint32_t timestamp;    /* unix epoch (UTC)                                  */
    int8_t   temperature;  /* whole degrees C, range: -128 to +127             */
    uint8_t  humidity;     /* whole % RH, range: 0 to 100                      */
    uint16_t crc;          /* CRC-16/CCITT over bytes [0..8]                    */
} WeatherPacket;

#define WEATHER_PACKET_SIZE    11
#define WEATHER_PACKET_VERSION  2

/*
 * StorageRecord — on-device flash record (6 bytes, packed)
 *
 * device_id omitted: implicit from device config.
 * crc omitted: flash controller ECC covers single-bit integrity.
 * Stored in a circular buffer; oldest records are overwritten when full.
 *
 * int8_t / uint8_t suffice: LM92 range is -128..+127 C, HDC3020 is 0..100% RH.
 * At 60-second intervals: 365 days = 525,600 records = ~3.15 MB flash.
 */
typedef struct __attribute__((packed)) {
    uint32_t timestamp;   /* unix epoch (UTC)              */
    int8_t   temperature; /* whole degrees C, -128..+127   */
    uint8_t  humidity;    /* whole % RH, 0..100            */
} StorageRecord;

#define STORAGE_RECORD_SIZE 6

/* Narrow sensor reads to storage types */
#define TEMP_TO_FIXED(t)   ((int8_t)(t))
#define HUM_TO_FIXED(h)    ((uint8_t)(h))

#endif /* WEATHER_TYPES_H */
