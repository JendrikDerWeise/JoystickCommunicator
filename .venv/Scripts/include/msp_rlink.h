/**
 * @file
 * @brief   Msp rlink
 * @ingroup MspLib
 *
 * @par Copyright
 * COPYRIGHT NOTICE: (c) 2023 mo-Vis
 * All rights reserved.
 */

/******************************************************************************
 * EXTERN C
 ******************************************************************************/
#ifdef __cplusplus
extern "C" {
#endif

/******************************************************************************
 * MULTIPLE INCLUSION GUARD
 ******************************************************************************/
#ifndef MSP_RLINK
/** Multiple inclusion guard */
#  define MSP_RLINK

/******************************************************************************
 * INCLUDE FILES
 ******************************************************************************/
#  include <stdint.h>
#  include <stdbool.h>
#  include <msp_rlinkdef.h>
#  include <msp_rlinkex.h>
#  include <msp_status.h>

/******************************************************************************
 * MACROS
 ******************************************************************************/
/** Disconnected event mask */
#  define MSP_RLINK_EV_DISCONNECTED 0x01

/** Error event mask */
#  define MSP_RLINK_EV_ERROR 0x02

/** Data ready event mask */
#  define MSP_RLINK_EV_DATA_READY 0x04

/******************************************************************************
 * TYPE DEFINITIONS
 ******************************************************************************/
/** Device info structure */
typedef struct msp_devinfo_s msp_rlink_devinfo_t;

/** Devices structure */
typedef struct msp_devices_s msp_rlink_devices_t;

/** Rlink handle */
typedef struct msp_rlink_s msp_rlink_t;

/******************************************************************************
 * FUNCTION DECLARATIONS
 ******************************************************************************/
/**
 * @param devinfo Device information
 *
 * @return The instance of NULL when failed.
 *
 * @details
 * Construct an instance.
 */
EXPORT msp_rlink_t* msp_rlink_Construct(msp_rlink_devinfo_t* devinfo);

/**
 * @param self The instance
 *
 * @details
 * Destruct the instance.
 */
EXPORT void msp_rlink_Destruct(msp_rlink_t* self);

/**
 * @param self The instance
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Open the rlink
 */
EXPORT msp_status_t msp_rlink_Open(msp_rlink_t* self);

/**
 * @param self The instance
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Close the device
 */
EXPORT msp_status_t msp_rlink_Close(msp_rlink_t* self);

/**
 * @param self The instance
 * @param x    X value to set
 * @param y    Y value to set
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 *  Set the Xy value
 */
EXPORT msp_status_t msp_rlink_SetXy(msp_rlink_t* self, int8_t x, int8_t y);

/**
 * @param self The instance
 * @param id   The axis id
 * @param dir  The axis direction
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 *  Set the axis value
 */
EXPORT msp_status_t msp_rlink_SetAxis(msp_rlink_t* self,
                                      msp_rlink_axis_id_t id,
                                      msp_rlink_axis_dir_t dir);

/**
 * @param self The instance
 * @param btn  Button id
 * @param pressed Pressed or not?
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 *  Set the button value
 */
EXPORT msp_status_t msp_rlink_SetBtn(msp_rlink_t* self,
                                     msp_rlink_btn_t btn,
                                     bool pressed);

/**
 * @param self The instance
 * @param enable Enable/disable the horn
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 *  Set the horn
 */
EXPORT msp_status_t msp_rlink_SetHorn(msp_rlink_t* self, bool enable);

/**
 * @param self The instance
 * @param light The light id
 * @param enable Enable/disable the light
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 *  Set the light
 */
EXPORT msp_status_t msp_rlink_SetLight(msp_rlink_t* self,
                                       msp_rlink_light_t light,
                                       bool enable);

/**
 * @param self The instance
 * @param error The error
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 *  Set the error (0 is no error)
 */
EXPORT msp_status_t msp_rlink_SetError(msp_rlink_t* self, uint8_t error);

/**
 * @param self The instance
 * @param m    Mode to get
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the mode
 */
EXPORT msp_status_t msp_rlink_GetMode(msp_rlink_t* self, msp_rlink_mode_t* m);

/**
 * @param self The instance
 * @param p    Profile to get
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the profile
 */
EXPORT msp_status_t msp_rlink_GetProfile(msp_rlink_t* self,
                                         msp_rlink_profile_t* p);

/**
 * @param self The instance
 * @param horn Horn status
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the horn status
 */
EXPORT msp_status_t msp_rlink_GetHorn(msp_rlink_t* self, bool* horn);

/**
 * @param self The instance
 * @param low  Battery low bit
 * @param gauge Battery gauge
 * @param current Battery current
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the battery status
 */
EXPORT msp_status_t msp_rlink_GetBatteryInfo(msp_rlink_t* self,
                                             bool* low,
                                             uint8_t* gauge,
                                             float* current);

/**
 * @param self The instance
 * @param m1vel Motor 1 velocity
 * @param m2vel Motor 2 velocity
 * @param turnVel Turn velocity
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the velocity variables
 */
EXPORT msp_status_t msp_rlink_GetVelocity(msp_rlink_t* self,
                                          float* m1vel,
                                          float* m2vel,
                                          float* turnVel);

/**
 * @param self The instance
 * @param speed  Speed value
 * @param trueSpeed  True speed
 * @param speedLimitApplied Is the speed limit applied
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the speed values
 */
EXPORT msp_status_t msp_rlink_GetSpeed(msp_rlink_t* self,
                                       uint8_t* speed,
                                       float* trueSpeed,
                                       uint8_t* speedLimitApplied);

/**
 * @param self The instance
 * @param light The light id
 * @param active Is the light active?
 * @param lit Is the light lit?
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the light values
 */
EXPORT msp_status_t msp_rlink_GetLight(msp_rlink_t* self,
                                       msp_rlink_light_t light,
                                       bool* active,
                                       bool* lit);

/**
 * @param self The instance
 * @param ecInterface Interface error code
 * @param ecRnet Rnet error code
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the error codes
 */
EXPORT msp_status_t msp_rlink_GetError(msp_rlink_t* self,
                                       uint16_t* ecInterface,
                                       uint16_t* ecRnet);

/**
 * @param self The instance
 * @param oon Out of neutral?
 * @param status RLink status
 * @param warning Warning occured?
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the status
 */
EXPORT msp_status_t msp_rlink_GetDevStatus(msp_rlink_t* self,
                                           bool* oon,
                                           msp_rlink_status_t* status,
                                           uint8_t* warning);

/**
 * @param self The instance
 * @param inputProcess Input process
 * @param interProcess Intermediate process
 * @param outputProcess Output process
 * @param selInput Selected input
 * @param selInter Selected intermediate
 * @param selOutput Selected output
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the status
 */
EXPORT msp_status_t msp_rlink_GetHms(msp_rlink_t* self,
                                     uint16_t* inputProcess,
                                     uint16_t* interProcess,
                                     uint16_t* outputProcess,
                                     bool* selInput,
                                     bool* selInter,
                                     bool* selOutput);

/**
 * @param self The instance
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Call this function to reset the timeout timer.
 */
EXPORT msp_status_t msp_rlink_Heartbeat(msp_rlink_t* self);

/**
 * @param self The instance
 * @param err The error code
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Get the latest error code
 */
EXPORT msp_status_t msp_rlink_GetLatestError(msp_rlink_t* self,
                                             msp_rlink_err_t* err);

/**
 * @param self The instance
 * @param mask The event flags that can be enabled
 * @param cvar Condiion variable
 * @param mutex Conditional variable mutex
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * As a client subscribe to these events if you want to be notified
 * when data is ready of an error was encountered.
 */
EXPORT msp_status_t msp_rlink_SetEventNotification(msp_rlink_t* self,
                                                   unsigned int mask,
                                                   void* cvar,
                                                   void* mutex);

/**
 * @param self The instance
 * @param flags The event flags that have been set
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * When an conditional variable has occured, use this function to check the
 * flag that triggered the conditional variable.
 *
 * If function is called from other thread with wait condition
 * call this function after the wait condition has locked the mutex
 * If you do not all this function wihtout a wait condition, you have to
 * surround the function with: lock_mutex/unlock_mutex
 */
EXPORT msp_status_t msp_rlink_GetStatus(msp_rlink_t* self, unsigned int* flags);

/**
 * @param self The instance
 * @param enable Enable/disable logging
 *
 * @details
 * Enable disable logging
 */
EXPORT void msp_rlink_Logging(msp_rlink_t* self, bool enable);

/**
 * @param self The instance
 * @param filename File to log to
 *
 * @retval false Failed to create log file
 * @retval true  Created logfile
 *
 * @details
 * Filename to log to
 */
EXPORT bool msp_rlink_SetLogFile(msp_rlink_t* self, const char* filename);

/**
 * @return Devices instance (NULL when failed)
 *
 * @details
 * Enumerate the connected rlink devices
 */
EXPORT msp_rlink_devices_t* msp_rlink_DevicesConstruct(void);

/**
 * @param devices Devices instance
 *
 * @details
 * Destruct the devices instance
 */
EXPORT void msp_rlink_DevicesDestruct(msp_rlink_devices_t* devices);

/**
 * @param devices Devices instance
 * @param nofDevices Returns the number of rlink devices connected
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Returns the number of rlink devices
 */
EXPORT msp_status_t msp_rlink_GetNumberOfDevices(msp_rlink_devices_t* devices,
                                                 size_t* nofDevices);

/**
 * @param devices Devices instance
 * @param index Index
 * @param sn Returns the serialnumber
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Returns the serialnumber of a certain device from the devices list
 */
EXPORT msp_status_t
msp_rlink_GetDeviceSerialnumber(msp_rlink_devices_t* devices,
                                size_t index,
                                char** sn);

/**
 * @param devices Devices instance
 * @param index Index
 * @param descr Returns the description
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Returns the serialnumber of a certain device from the devices list
 */
EXPORT msp_status_t msp_rlink_GetDeviceDescription(msp_rlink_devices_t* devices,
                                                   size_t index,
                                                   char** descr);

/**
 * @param devices Devices
 * @param index Device index
 * @param devinfo Returns the device info
 *
 * @return Every non MSP_OK return code indicates a fail
 *
 * @details
 * Returns the device info of a certain device in the devices list
 */
EXPORT msp_status_t msp_rlink_GetDevice(msp_rlink_devices_t* devices,
                                        size_t index,
                                        msp_rlink_devinfo_t** devinfo);

/******************************************************************************
 * END OF MULTIPLE INCLUSION GUARD
 ******************************************************************************/
#endif

/******************************************************************************
 * END OF EXTERN C
 ******************************************************************************/
#ifdef __cplusplus
}
#endif

/******************************************************************************
 * END OF FILE
 ******************************************************************************/
