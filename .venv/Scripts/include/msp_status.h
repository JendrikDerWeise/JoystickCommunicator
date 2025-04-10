/**
 * @file
 * @brief   MSP status definition
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
#ifndef MSP_STATUS
/** Multiple inclusion guard */
#  define MSP_STATUS

/******************************************************************************
 * TYPE DEFINITIONS
 ******************************************************************************/
/** MSP status */
typedef enum {
  MSP_OK, /**< No error */

  MSP_FTD2XX, /**< Driver error */
  MSP_TIMEOUT, /**< Timeout */
  MSP_OVERFLOW, /**< Buffer overflow */
  MSP_UNDERFLOW, /**< Buffer underflow */
  MSP_INVALID_ARGS, /**< Invalid arguments */
  MSP_NOT_SUPPORTED, /**< Not supported */
  MSP_OTHER_ERROR, /**< Unknown error */
  MSP_NO_MEMORY, /**< Out of memory */
  MSP_NULL_PTR, /**< NULL pointer received */
  MSP_INVALID_SIZE, /**< Invalid size */
  MSP_NOT_FOUND, /**< Resource not found */
  MSP_BUSY, /**< Busy */
  MSP_MSG_ERR, /**< Message error */
  MSP_CRC_ERR, /**< CRC error */
  MSP_INVALID_LEN, /**< CRC error */
} msp_status_t;

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
