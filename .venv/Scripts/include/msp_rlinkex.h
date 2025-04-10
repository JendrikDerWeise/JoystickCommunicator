/**
 * @file
 * @brief   Msp rlink export/import
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
#ifndef MSP_RLINKEX_H_
/** Multiple inclusion guard */
#  define MSP_RLINKEX_H_

/******************************************************************************
 * MACROS
 ******************************************************************************/
#  if defined(TEST) || defined(DOXYGEN)
/**
 * The compiler is able to generate better code because it can determine
 * whether a function exists in a DLL or not,
 */
#    ifndef EXPORT
#      define EXPORT
#    endif
/**
 * Windows compatibility: was added to provide an easy way to export functions
 * from an .exe or .dll file without using a .def file.
 */
#    ifndef IMPORT
#      define IMPORT
#    endif
#  elif defined(__linux__)
#    ifndef EXPORT
#      define EXPORT __attribute__((visibility("default")))
#    endif
#    ifndef IMPORT
#      define IMPORT
#    endif
#  elif defined(_WIN32)
#    ifndef EXPORT
#      define EXPORT __declspec(dllexport)
#    endif
#    ifndef IMPORT
#      define IMPORT __declspec(dllimport)
#    endif
#  else
#    error "Unknown platform"
#  endif

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
