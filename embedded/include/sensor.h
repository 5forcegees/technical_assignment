#ifndef SENSOR_H
#define SENSOR_H

#include <stdint.h>
#include "weather_types.h"

/*
 * Sensor HAL — abstracts LM92 (temperature) and HDC3020 (humidity).
 *
 * On real hardware these would perform I2C transactions.
 * The mock implementation (sensor_mock.c) generates deterministic values
 * for host-side testing without physical devices.
 */

typedef struct {
    int16_t  temperature; /* whole degrees C */
    uint16_t humidity;    /* whole % RH      */
    uint8_t  valid;       /* 1 if read succeeded, 0 on I2C error */
} SensorReading;

/* Initialise sensor peripherals. Returns 0 on success, -1 on error. */
int sensor_init(void);

/* Read both sensors atomically. Populates reading; sets valid=0 on failure. */
void sensor_read(SensorReading *reading);

#endif /* SENSOR_H */
