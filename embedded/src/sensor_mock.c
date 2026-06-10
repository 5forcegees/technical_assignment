#include "sensor.h"
#include <math.h>

/*
 * Mock sensor implementation for host-side testing.
 * Generates a slowly varying sine-wave temperature (15-30 C)
 * and a triangular humidity (40-80% RH) keyed to a call counter.
 * No I2C hardware required.
 */

static uint32_t call_count = 0;

int sensor_init(void)
{
    call_count = 0;
    return 0;
}

void sensor_read(SensorReading *reading)
{
    float t_deg = 22.5f + 7.5f * sinf((float)call_count * 0.01f);
    float h_pct = 60.0f + 20.0f * sinf((float)call_count * 0.007f + 1.0f);

    reading->temperature = TEMP_TO_FIXED(t_deg);
    reading->humidity    = HUM_TO_FIXED(h_pct);
    reading->valid       = 1;

    call_count++;
}
