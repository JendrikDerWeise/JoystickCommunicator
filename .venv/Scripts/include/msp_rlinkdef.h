/**
 * @file
 * @brief   Msp rlink definitions
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
#ifndef MSP_RLINKDEF
/** Multiple inclusion guard */
#  define MSP_RLINKDEF

/******************************************************************************
 * TYPE DEFINITIONS
 ******************************************************************************/
/** Button enumeration */
typedef enum msp_rlink_btn_e {
  MSP_RLINK_BTN_YT,  /**< yellow tip */
  MSP_RLINK_BTN_YR,  /**< Yellow ring */
  MSP_RLINK_BTN_RR,  /**< Red ring */
  MSP_RLINK_BTN_NOF, /**< Number of buttons */
} msp_rlink_btn_t;

/** Light enumeration */
typedef enum msp_rlink_light_e {
  MSP_RLINK_LIGHT_BRAKE,  /**< Brake light */
  MSP_RLINK_LIGHT_DIP,    /**< Dip light */
  MSP_RLINK_LIGHT_HAZARD, /**< Hazard light */
  MSP_RLINK_LIGHT_LEFT,   /**< Left light */
  MSP_RLINK_LIGHT_RIGHT,  /**< Right light */
  MSP_RLINK_LIGHT_NOF,    /**< Number of lights */
} msp_rlink_light_t;

/** Mode enumeration */
typedef enum msp_rlink_mode_e {
  MSP_RLINK_MODE_1,   /**< Mode 1 */
  MSP_RLINK_MODE_2,   /**< Mode 2 */
  MSP_RLINK_MODE_3,   /**< Mode 3 */
  MSP_RLINK_MODE_4,   /**< Mode 4 */
  MSP_RLINK_MODE_5,   /**< Mode 5 */
  MSP_RLINK_MODE_6,   /**< Mode 6 */
  MSP_RLINK_MODE_7,   /**< Mode 7 */
  MSP_RLINK_MODE_8,   /**< Mode 8 */
  MSP_RLINK_MODE_NOF, /**< Number of modes */
} msp_rlink_mode_t;

/** Profile enumeration */
typedef enum msp_rlink_profile_e {
  MSP_RLINK_PROFILE_1,   /**< Profile 1 */
  MSP_RLINK_PROFILE_2,   /**< Profile 2 */
  MSP_RLINK_PROFILE_3,   /**< Profile 3 */
  MSP_RLINK_PROFILE_4,   /**< Profile 4 */
  MSP_RLINK_PROFILE_5,   /**< Profile 5 */
  MSP_RLINK_PROFILE_6,   /**< Profile 6 */
  MSP_RLINK_PROFILE_7,   /**< Profile 7 */
  MSP_RLINK_PROFILE_8,   /**< Profile 8 */
  MSP_RLINK_PROFILE_NOF, /**< Number of profiles */
} msp_rlink_profile_t;

/** Rlink status */
typedef enum msp_rlink_status_e {
  MSP_RLINK_STATUS_CONFIGURING,  /**< Configuring */
  MSP_RLINK_STATUS_ERROR,        /**< Error */
  MSP_RLINK_STATUS_POWER_CYCLE,  /**< Power cycle */
  MSP_RLINK_STATUS_SHUTDOWN,     /**< Shutdown */
  MSP_RLINK_STATUS_OUT_OF_FOCUS, /**< Out of focus */
  MSP_RLINK_STATUS_FOCUS,        /**< Focus */
  MSP_RLINK_STATUS_NOF,          /**< Number of status */
} msp_rlink_status_t;

/** Axis id enumeration */
typedef enum msp_rlink_axis_id_e {
  MSP_RLINK_AXIS_ID_0,   /**< Axis id 0 */
  MSP_RLINK_AXIS_ID_1,   /**< Axis id 1 */
  MSP_RLINK_AXIS_ID_2,   /**< Axis id 2 */
  MSP_RLINK_AXIS_ID_3,   /**< Axis id 3 */
  MSP_RLINK_AXIS_ID_4,   /**< Axis id 4 */
  MSP_RLINK_AXIS_ID_5,   /**< Axis id 5 */
  MSP_RLINK_AXIS_ID_6,   /**< Axis id 6 */
  MSP_RLINK_AXIS_ID_7,   /**< Axis id 7 */
  MSP_RLINK_AXIS_ID_8,   /**< Axis id 8 */
  MSP_RLINK_AXIS_ID_9,   /**< Axis id 9 */
  MSP_RLINK_AXIS_ID_10,  /**< Axis id 10 */
  MSP_RLINK_AXIS_ID_11,  /**< Axis id 11 */
  MSP_RLINK_AXIS_ID_12,  /**< Axis id 12 */
  MSP_RLINK_AXIS_ID_13,  /**< Axis id 13 */
  MSP_RLINK_AXIS_ID_14,  /**< Axis id 14 */
  MSP_RLINK_AXIS_ID_15,  /**< Axis id 15 */
  MSP_RLINK_AXIS_ID_16,  /**< Axis id 16 */
  MSP_RLINK_AXIS_ID_17,  /**< Axis id 17 */
  MSP_RLINK_AXIS_ID_18,  /**< Axis id 18 */
  MSP_RLINK_AXIS_ID_19,  /**< Axis id 19 */
  MSP_RLINK_AXIS_ID_20,  /**< Axis id 20 */
  MSP_RLINK_AXIS_ID_21,  /**< Axis id 21 */
  MSP_RLINK_AXIS_ID_22,  /**< Axis id 22 */
  MSP_RLINK_AXIS_ID_23,  /**< Axis id 23 */
  MSP_RLINK_AXIS_ID_24,  /**< Axis id 24 */
  MSP_RLINK_AXIS_ID_25,  /**< Axis id 25 */
  MSP_RLINK_AXIS_ID_26,  /**< Axis id 26 */
  MSP_RLINK_AXIS_ID_27,  /**< Axis id 27 */
  MSP_RLINK_AXIS_ID_28,  /**< Axis id 28 */
  MSP_RLINK_AXIS_ID_29,  /**< Axis id 29 */
  MSP_RLINK_AXIS_ID_30,  /**< Axis id 30 */
  MSP_RLINK_AXIS_ID_31,  /**< Axis id 31 */
  MSP_RLINK_AXIS_ID_NOF, /**< Number of axes */
} msp_rlink_axis_id_t;

/** Axis directions */
typedef enum msp_rlink_axis_dir_e {
  MSP_RLINK_AXIS_DIR_NONE = 0, /**< No movement */
  MSP_RLINK_AXIS_DIR_UP,       /**< Upwards movement */
  MSP_RLINK_AXIS_DIR_DOWN,     /**< Downwards movement */
  MSP_RLINK_AXIS_DIR_NOF,      /**< Number of movements */
} msp_rlink_axis_dir_t;

/** Rlink error indicators */
typedef enum msp_rlink_err_e {
  MSP_RLINK_ERR_NONE = 0,      /**< No error */
  MSP_RLINK_ERR_TIMEOUT,       /**< Timeout error */
  MSP_RLINK_ERR_OUT_OF_MEMORY, /**< Out of memory error */
  MSP_RLINK_ERR_MDEV_ERROR,    /**< Master device error */
} msp_rlink_err_t;

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
