#include <stdio.h>
#include <stdint.h>
#include <time.h>

#include "weather_types.h"
#include "weather_packet.h"
#include "circular_buffer.h"
#include "sensor.h"
#include "mqtt_client.h"

#define DEVICE_ID        42
#define BROKER_HOST      "iot.example.amazonaws.com"
#define BROKER_PORT      8883
#define MQTT_TOPIC       "weather-stations/42/data"
#define SAMPLE_INTERVAL  60   /* seconds */

/*
 * Backing store for the circular buffer.
 * On real hardware this would be a memory-mapped external flash region.
 * Declared static to avoid stack overflow on Cortex-M3.
 *
 * Size: 525,600 * 6 bytes = ~3.15 MB — requires external flash.
 * 
 */
static StorageRecord flash_store[CIRCULAR_BUFFER_CAPACITY];
static CircularBuffer buffer;

static uint32_t now_unix(void)
{
    return (uint32_t)time(NULL);
}

int main(void)
{
    sensor_init();
    cb_init(&buffer, flash_store, CIRCULAR_BUFFER_CAPACITY);
    mqtt_connect(BROKER_HOST, BROKER_PORT, "station-42");

    printf("Weather station simulator running (Ctrl-C to stop)\n");

    while (1) {
        SensorReading reading;
        sensor_read(&reading);

        if (!reading.valid) {
            fprintf(stderr, "[WARN] sensor read failed, skipping\n");
            /* In production: increment error counter, alert if threshold exceeded */
            continue;
        }

        uint32_t ts = now_unix();

        /* Store locally first — guarantees data is not lost if MQTT fails */
        StorageRecord rec = { ts, TEMP_TO_FIXED(reading.temperature),
                                  HUM_TO_FIXED(reading.humidity) };
        cb_write(&buffer, &rec);

        /* Transmit */
        WeatherPacket pkt = weather_packet_create(
            DEVICE_ID, ts, TEMP_TO_FIXED(reading.temperature),
                           HUM_TO_FIXED(reading.humidity));

        uint8_t buf[WEATHER_PACKET_SIZE];
        weather_packet_serialize(&pkt, buf);

        if (mqtt_publish(MQTT_TOPIC, buf, WEATHER_PACKET_SIZE) != 0) {
            fprintf(stderr, "[WARN] MQTT publish failed — data retained in buffer\n");
        }

        printf("[INFO] ts=%u  temp=%d C  hum=%u%%  buf=%u/%lu\n",
               ts,
               (int)reading.temperature,
               (unsigned)reading.humidity,
               cb_count(&buffer),
               (unsigned long)CIRCULAR_BUFFER_CAPACITY);

        /* In production: replace with hardware timer / RTOS sleep */
        struct timespec req = { SAMPLE_INTERVAL, 0 };
        nanosleep(&req, NULL);
    }

    mqtt_disconnect();
    return 0;
}
