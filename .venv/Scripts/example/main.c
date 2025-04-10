/******************************************************************************
 * INCLUDE FILES
 ******************************************************************************/
#include <stdlib.h>
#include <string.h>
#include <msp_core.h>

#if defined(_WIN32)
#  include <windows.h>
#  include <conio.h>
#endif

#include <stdio.h>
#include <msp_rlink.h>

/******************************************************************************
 * MACROS
 ******************************************************************************/
#if 1
#  if defined(_MSC_VER)
#    define DBG_PRINT(fmt, ...)  do {                                          \
                                   fprintf(stdout, fmt, ##__VA_ARGS__);        \
                                 } while(0)
#  elif defined(__GNUC__)
#    define DBG_PRINT(fmt, args...) fprintf(stdout, fmt, ##args)
#  endif
#else
#  define DBG_PRINT(fmt, ...)
#endif

#define CONSOLE_BFR_SIZE (256)
#define FLAG_USER_QUIT 0x01 // User has typed exit in the console
#define FLAG_CONSOLE_QUIT 0x02 // Stop running the console thread
#define FLAG_WHEELCHAIR_QUIT 0x04 // stop running the wheelchair thread
#define FLAG_WHEELCHAIR_HEARTBEAT 0x08 // Send/Do no longer send heartbeats

/******************************************************************************
 * TYPE DEFINTIIONS
 ******************************************************************************/
typedef enum action_e {
  ACTION_UP,
  ACTION_DOWN,
  ACTION_LEFT,
  ACTION_RIGHT,
  ACTION_NEUTRAL,
  ACTION_BUTTON_PRESS,
  ACTION_BUTTON_RELEASE,
  ACTION_TOGGLE_LIGHT_BRAKE,
  ACTION_TOGGLE_LIGHT_DIP,
  ACTION_TOGGLE_LIGHT_HAZARD,
  ACTION_TOGGLE_LIGHT_LEFT,
  ACTION_TOGGLE_LIGHT_RIGHT,
  ACTION_TOGGLE_HORN,
  ACTION_AXIS_0_UP,
  ACTION_AXIS_0_DOWN,
  ACTION_AXIS_0_STOP,
  ACTION_TOGGLE_HB,
  ACTION_TRIGGER_ERROR,
  ACTION_DUMP,
  ACTION_QUIT,
  ACTION_NOF,
} action_t;

typedef struct {
  struct {
    bool oon;
    msp_rlink_status_t status;
    uint8_t warning;
  } status;

  struct {
    msp_rlink_mode_t mode;
    msp_rlink_profile_t profile;
    uint16_t inputProcess;
    uint16_t interProcess;
    uint16_t outputProcess;
    bool selInput;
    bool selInter;
    bool selOutput;
  } hms;

  bool horn;

  struct {
    bool low;
    uint8_t gauge;
    float current;
  } battery;

  struct {
    float m1Vel;
    float m2Vel;
    float turnVel;
  } velocity;

  struct {
    uint8_t speed;
    float trueSpeed;
    uint8_t speedLimitApplied;
  } speed;

  struct {
    bool active;
    bool lit;
  } light[MSP_RLINK_LIGHT_NOF];
} incoming_t;

typedef struct {
  int8_t x;
  int8_t y;
  bool btn;
  bool light[MSP_RLINK_LIGHT_NOF];
  bool horn;
  msp_rlink_axis_dir_t axis0;
  uint8_t error;
} outgoing_t;

typedef struct {
  struct {
    unsigned int flags;
    msp_sig_t* signal;
  } main;

  struct {
    unsigned int flags;
    msp_sig_t* signal;
    msp_sem_t* started;
    msp_sem_t* stopped;
    msp_trd_t* thread;
  } wheelchair;

  struct {
    unsigned int flags;
    msp_sig_t* signal;
    msp_sem_t* started;
    msp_sem_t* stopped;
    msp_trd_t* thread;
  } console;

  void* rlink;

  struct {
    incoming_t content;
    msp_mtx_t* cs; // mutex
  } incoming;

  struct {
    outgoing_t content;
    msp_mtx_t* cs; // mutex
  } outgoing;
} main_cb_t;

typedef enum {
  CONSOLE_SELECT_STATUS_OK,
  CONSOLE_SELECT_STATUS_QUIT,
  CONSOLE_SELECT_STATUS_ERR,
} console_select_status_t;

typedef enum {
  CONSOLE_SELECTION_DEV,
  CONSOLE_SELECTION_NOF,
} console_selection_t;

typedef struct {
  const char* name;
  const char** options;
  size_t nofOptions;
} console_tbl_t;

#if defined(__linux__)

#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

struct termios orig_termios;

void reset_terminal_mode() {
    tcsetattr(0, TCSANOW, &orig_termios);
}

void set_conio_terminal_mode() {
    struct termios new_termios;

    /* take two copies - one for now, one for later */
    tcgetattr(0, &orig_termios);
    memcpy(&new_termios, &orig_termios, sizeof(new_termios));

    /* register cleanup handler, and set the new terminal mode */
    atexit(reset_terminal_mode);
    cfmakeraw(&new_termios);
    tcsetattr(0, TCSANOW, &new_termios);
}

int _kbhit() {
    struct timeval tv = { 0L, 0L };
    fd_set fds;
    FD_ZERO(&fds);
    FD_SET(0, &fds);
    return select(1, &fds, NULL, NULL, &tv) > 0;
}

int _getch() {
    int r;
    unsigned char c;
    if ((r = read(0, &c, sizeof(c))) < 0) {
        return r;
    } else {
        return c;
    }
}
#endif

static void SignalToggleHeartbeat(main_cb_t* self) {
  msp_sig_MutexLock(self->wheelchair.signal);
  self->wheelchair.flags |= FLAG_WHEELCHAIR_HEARTBEAT;
  msp_sig_CondVarSignal(self->wheelchair.signal);
  msp_sig_MutexUnlock(self->wheelchair.signal);
}

static void SignalUserWantsToQuit(main_cb_t* self) {
  msp_sig_MutexLock(self->main.signal);
  self->main.flags |= FLAG_USER_QUIT;
  msp_sig_CondVarSignal(self->main.signal);
  msp_sig_MutexUnlock(self->main.signal);
}
static void SignalConsoleQuit(main_cb_t* self) {
  msp_sig_MutexLock(self->console.signal);
  self->console.flags |= FLAG_CONSOLE_QUIT;
  msp_sig_CondVarSignal(self->console.signal);
  msp_sig_MutexUnlock(self->console.signal);
}

static void SignalWheelChairQuit(main_cb_t* self) {
  msp_sig_MutexLock(self->wheelchair.signal);
  self->wheelchair.flags |= FLAG_WHEELCHAIR_QUIT;
  msp_sig_CondVarSignal(self->wheelchair.signal);
  msp_sig_MutexUnlock(self->wheelchair.signal);
}

static void PrintActions() {
  char* tbl[ACTION_NOF] = {
      "up",
      "down",
      "left",
      "right",
      "neutral",
      "button press",
      "button release",
      "toggle light brake",
      "toggle light dip",
      "toggle light hazard",
      "toggle light left",
      "toggle light right",
      "toggle horn",
      "axis 0 up",
      "axis 0 down",
      "axis 0 stop",
      "toggle heartbeat",
      "trigger error",
      "dump",
      "quit",
  };

  printf(
      "The following actions to the control the wheelchair are supported:\n");
  for (size_t i = 0; i < ACTION_NOF; i++) {
    printf("%3zu: %s\n", i, tbl[i]);
  }
  printf("Enter action number: ");
}


static action_t StrToAction(char* str) {
  // Try to convert it to an integer
  char* start = str;
  char* end = NULL;
  int value = strtol(start, &end, 10);

  // Test the input
  if ((start == end) && (value >= ACTION_NOF)) {
    value = ACTION_NOF;
  }

  return (action_t)value;
}

static void ExecuteAction(main_cb_t* self, action_t action) {
  switch (action) {
    case ACTION_UP:
      msp_mtx_Lock(self->outgoing.cs);
      if (self->outgoing.content.y < 100) {
        self->outgoing.content.y += 20;
      }
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_DOWN:
      msp_mtx_Lock(self->outgoing.cs);
      if (-100 < self->outgoing.content.y) {
        self->outgoing.content.y -= 20;
      }
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_LEFT:
      msp_mtx_Lock(self->outgoing.cs);
      if (-100 < self->outgoing.content.x) {
        self->outgoing.content.x -= 20;
      }
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_RIGHT:
      msp_mtx_Lock(self->outgoing.cs);
      if (self->outgoing.content.x < 100) {
        self->outgoing.content.x += 20;
      }
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_NEUTRAL:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.x = 0;
      self->outgoing.content.y = 0;
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_BUTTON_PRESS:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.btn = true;
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_BUTTON_RELEASE:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.btn = false;
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_TOGGLE_LIGHT_BRAKE:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.light[MSP_RLINK_LIGHT_BRAKE] =
          !self->outgoing.content.light[MSP_RLINK_LIGHT_BRAKE];
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_TOGGLE_LIGHT_DIP:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.light[MSP_RLINK_LIGHT_DIP] =
          !self->outgoing.content.light[MSP_RLINK_LIGHT_DIP];
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_TOGGLE_LIGHT_HAZARD:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.light[MSP_RLINK_LIGHT_HAZARD] =
          !self->outgoing.content.light[MSP_RLINK_LIGHT_HAZARD];
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_TOGGLE_LIGHT_LEFT:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.light[MSP_RLINK_LIGHT_LEFT] =
          !self->outgoing.content.light[MSP_RLINK_LIGHT_LEFT];
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_TOGGLE_LIGHT_RIGHT:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.light[MSP_RLINK_LIGHT_RIGHT] =
          !self->outgoing.content.light[MSP_RLINK_LIGHT_RIGHT];
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_TOGGLE_HORN:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.horn = !self->outgoing.content.horn;
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_AXIS_0_UP:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.axis0 = MSP_RLINK_AXIS_DIR_UP;
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_AXIS_0_DOWN:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.axis0 = MSP_RLINK_AXIS_DIR_DOWN;
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_AXIS_0_STOP:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.axis0 = MSP_RLINK_AXIS_DIR_NONE;
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_TOGGLE_HB:
      SignalToggleHeartbeat(self);
      break;

    case ACTION_TRIGGER_ERROR:
      msp_mtx_Lock(self->outgoing.cs);
      self->outgoing.content.error = 0x01; // value different from 0
      msp_mtx_Unlock(self->outgoing.cs);
      break;

    case ACTION_DUMP: {
      incoming_t content;
      msp_mtx_Lock(self->incoming.cs);
      memcpy(&content, &self->incoming.content, sizeof(incoming_t));
      msp_mtx_Unlock(self->incoming.cs);

      char* sStatus[MSP_RLINK_STATUS_NOF] = {
          "CONFIGURING",
          "ERROR",
          "POWER_CYCLE",
          "SHUTDOWN",
          "OUT_OF_FOCUS",
          "FOCUS",
      };

      printf("\n");
      printf("Status\n");
      printf(" - oon:               %d\n", content.status.oon);
      printf(" - status:            %s\n", sStatus[content.status.status]);
      printf(" - warning:           %02x\n", content.status.warning);

      printf("\n");
      printf("Battery\n");
      printf(" - low:               %d\n", content.battery.low);
      printf(" - gauge:             %d\n", content.battery.gauge);
      printf(" - current:           %.2f A\n", content.battery.current);

      printf("\n");
      printf("Host modal selection\n");
      printf(" - mode:              %u\n", content.hms.mode);
      printf(" - profile:           %u\n", content.hms.profile);
      printf(" - inputProcess:      %04x\n", content.hms.inputProcess);
      printf(" - interProcess:      %04x\n", content.hms.interProcess);
      printf(" - outputProcess:     %04x\n", content.hms.outputProcess);
      printf(" - selInput:          %u\n", content.hms.selInput);
      printf(" - selInter:          %u\n", content.hms.selInter);
      printf(" - selOutput:         %u\n", content.hms.selOutput);

      printf("\n");
      printf("Horn\n");
      printf(" - horn:              %d\n", content.horn);

      printf("\n");
      printf("Velocity\n");
      printf(" - m1Vel:             %.2f rad/s\n", content.velocity.m1Vel);
      printf(" - m2Vel:             %.2f rad/s\n", content.velocity.m2Vel);
      printf(" - turnVel:           %.2f rad/s\n", content.velocity.turnVel);

      printf("\n");
      printf("Speed\n");
      printf(" - speed:             %u\n", content.speed.speed);
      printf(" - trueSpeed:         %.2f km/h\n",
             content.speed.trueSpeed * 3.6);
      printf(" - speedLimitApplied: %d\n", content.speed.speedLimitApplied);

      printf("\n");
      printf("Brake light\n");
      printf(" - active:            %d\n",
             content.light[MSP_RLINK_LIGHT_BRAKE].active);
      printf(" - lit:               %d\n",
             content.light[MSP_RLINK_LIGHT_BRAKE].lit);

      printf("\n");
      printf("Dip light\n");
      printf(" - active:            %d\n",
             content.light[MSP_RLINK_LIGHT_DIP].active);
      printf(" - lit:               %d\n",
             content.light[MSP_RLINK_LIGHT_DIP].lit);

      printf("\n");
      printf("Hazard light\n");
      printf(" - active:            %d\n",
             content.light[MSP_RLINK_LIGHT_HAZARD].active);
      printf(" - lit:               %d\n",
             content.light[MSP_RLINK_LIGHT_HAZARD].lit);

      printf("\n");
      printf("Left light\n");
      printf(" - active:            %d\n",
             content.light[MSP_RLINK_LIGHT_LEFT].active);
      printf(" - lit:               %d\n",
             content.light[MSP_RLINK_LIGHT_LEFT].lit);

      printf("\n");
      printf("Right light\n");
      printf(" - active:            %d\n",
             content.light[MSP_RLINK_LIGHT_RIGHT].active);
      printf(" - lit:               %d\n",
             content.light[MSP_RLINK_LIGHT_RIGHT].lit);
    } break;

    default:
      break;
  }
}

static MSP_TRD_RET_TYPE ThreadConsole(MSP_TRD_ARG_TYPE args) {
  bool running = true;
  main_cb_t* self = (main_cb_t*)args;
  char bfr[CONSOLE_BFR_SIZE];
  unsigned int cnt = 0;
  memset(bfr, 0, CONSOLE_BFR_SIZE);

  msp_sem_Post(self->console.started);
  msp_sig_MutexLock(self->console.signal);

  #if defined(__linux__)
  set_conio_terminal_mode();
  #endif

  // Print the actions for the first time
  PrintActions();

  while (running) {
    msp_sigs_t sigs = msp_sig_CondVarWaitTimed(self->console.signal, 10);

    switch (sigs) {
      case MSP_SIGS_OK:
        if (self->console.flags & FLAG_CONSOLE_QUIT) {
          DBG_PRINT("TCONS: console quit\n");
          self->console.flags ^= FLAG_CONSOLE_QUIT;
          running = false;
          continue;
        }
        break;

      case MSP_SIGS_TIMEOUT: {
        if (_kbhit()) {
          int ch = _getch();

          switch (ch) {
            case '\r':
            case '\n': {
              printf("\n");
              bfr[cnt] = '\0';

              int action = StrToAction(bfr);

              if (action == ACTION_NOF) {
                printf("Invalid input\n");
                PrintActions();
              } else if (action == ACTION_QUIT) {
                running = false; // Lets quit
                SignalUserWantsToQuit(self);
              } else {
                ExecuteAction(self, action);
                PrintActions();
              }

              // Reset for the next command
              cnt = 0;
              memset(bfr, 0, CONSOLE_BFR_SIZE);
            } break;

            default:
              printf("%c", ch);

              if (cnt < CONSOLE_BFR_SIZE) {
                // Append the char to the buffer
                bfr[cnt++] = ch;
              } else {
                // User is overflowing
                // Just overwrite the last char and wait for a newline
                bfr[cnt] = ch;
              }
              break;
          }
        }
      } break;

      default:
        DBG_PRINT("TCONS: Encountered error\n");
        running = false;
        continue;
        break;
    }
  }

  msp_sig_MutexUnlock(self->console.signal);
  msp_sem_Post(self->console.stopped);

  return MSP_TRD_RET_VAL;
}


static MSP_TRD_RET_TYPE ThreadWheelchair(MSP_TRD_ARG_TYPE args) {
  main_cb_t* self = (main_cb_t*)args;
  bool running = true;
  bool heartbeat = true;
  outgoing_t previous;
  memset(&previous, 0, sizeof(outgoing_t));

  msp_sem_Post(self->wheelchair.started);
  msp_sig_MutexLock(self->wheelchair.signal);

  while (running) {
    msp_sigs_t sigs = msp_sig_CondVarWaitTimed(self->wheelchair.signal, 40);

    switch(sigs) {
      case MSP_SIGS_OK:
        if (self->wheelchair.flags & FLAG_WHEELCHAIR_QUIT) {
          DBG_PRINT("TCHAI: quit\n");
          self->wheelchair.flags ^= FLAG_WHEELCHAIR_QUIT;
          running = false;
          continue;
        }

        if (self->wheelchair.flags & FLAG_WHEELCHAIR_HEARTBEAT) {
          self->wheelchair.flags ^= FLAG_WHEELCHAIR_HEARTBEAT;
          heartbeat = !heartbeat;

          if (heartbeat) {
            DBG_PRINT("TCHAI: heartbeat enabled\n");
          } else {
            DBG_PRINT("TCHAI: heartbeat disabled\n");
          }
        }
        break;

      case MSP_SIGS_TIMEOUT: {
        outgoing_t content;

        msp_mtx_Lock(self->outgoing.cs);
        memcpy(&content, &self->outgoing.content, sizeof(outgoing_t));
        msp_mtx_Unlock(self->outgoing.cs);

        if (heartbeat) {
          msp_rlink_Heartbeat(self->rlink);
        }

        if ((previous.x != content.x) || (previous.y != content.y)) {
          DBG_PRINT("TCHAI: x:%d y:%d\n", content.x, content.y);
          msp_rlink_SetXy(self->rlink, content.x, content.y);
        }

        if (previous.btn != content.btn) {
          DBG_PRINT("TCHAI: btn:%d\n", content.btn);
          msp_rlink_SetBtn(self->rlink, MSP_RLINK_BTN_YT, content.btn);
        }

        if (previous.horn != content.horn) {
          DBG_PRINT("TCHAI: horn:%d\n", content.horn);
          msp_rlink_SetHorn(self->rlink, content.horn);
        }

        for (uint8_t id = 0; id < MSP_RLINK_LIGHT_NOF; id++) {
          if (previous.light[id] != content.light[id]) {
            DBG_PRINT("TCHAI: light-%d %d\n", id, content.light[id]);
            msp_rlink_SetLight(self->rlink, id, content.light[id]);
          }
        }

        if (previous.axis0 != content.axis0) {
          DBG_PRINT("TCHAI: axis0:%d\n", content.axis0);
          msp_rlink_SetAxis(self->rlink, MSP_RLINK_AXIS_ID_0, content.axis0);
        }

        if (previous.error != content.error) {
          DBG_PRINT("TCHAI: send error %04x\n", content.error);
          msp_rlink_SetError(self->rlink, content.error);
        }

        // Store so we can compare next cycle
        memcpy(&previous, &content, sizeof(outgoing_t));
      } break;

      default:
        DBG_PRINT("TCHAI: Error\n");
        running = false;
        continue;
        break;
    }
  } // while

  msp_sig_MutexUnlock(self->wheelchair.signal);
  msp_sem_Post(self->wheelchair.stopped);

  return MSP_TRD_RET_VAL;
}

static MSP_TRD_RET_TYPE ThreadMain(MSP_TRD_ARG_TYPE args) {
  main_cb_t* self = (main_cb_t*)args;
  bool running = true;

  msp_sig_MutexLock(self->main.signal);

  while (running) {
    msp_sigs_t sigs = msp_sig_CondVarWait(self->main.signal);

    switch (sigs) {
      case MSP_SIGS_OK: {
        if (self->main.flags & FLAG_USER_QUIT) {
          DBG_PRINT("TMAIN: user quit\n");
          self->main.flags ^= FLAG_USER_QUIT;
          SignalWheelChairQuit(self);
          // SignalConsoleQuit(self);
          running = false;
          continue;
        }

        // Rlink flags
        unsigned int flags = 0;
        if (MSP_OK == msp_rlink_GetStatus(self->rlink, &flags)) {
          if (flags & MSP_RLINK_EV_ERROR) {
            DBG_PRINT("TMAIN: rlink error\n");
            SignalWheelChairQuit(self);
            SignalConsoleQuit(self);
            //Beep(1000, 300);
            running = false;
            continue;
          }

          if (flags & MSP_RLINK_EV_DISCONNECTED) {
            DBG_PRINT("TMAIN: rlink disconnected\n");
            SignalWheelChairQuit(self);
            SignalConsoleQuit(self);
            //Beep(1000, 300);
            running = false;
            continue;
          }

          if (flags & MSP_RLINK_EV_DATA_READY) {
            // DBG_PRINT("TMAIN: rlink data available\n");
            incoming_t content;

            if (MSP_OK != msp_rlink_GetDevStatus(
                              self->rlink,
                              &content.status.oon,
                              &content.status.status,
                              &content.status.warning)) {
              DBG_PRINT("TMAIN: Failed to retrieve status info\n");
            }

            if (MSP_OK != msp_rlink_GetMode(self->rlink, &content.hms.mode)) {
              DBG_PRINT("TMAIN: Failed to retrieve mode info\n");
            }

            if (MSP_OK !=
                msp_rlink_GetProfile(self->rlink, &content.hms.profile)) {
              DBG_PRINT("TMAIN: Failed to retrieve profile info\n");
            }

            if (MSP_OK != msp_rlink_GetHms(self->rlink,
                                           &content.hms.inputProcess,
                                           &content.hms.interProcess,
                                           &content.hms.outputProcess,
                                           &content.hms.selInput,
                                           &content.hms.selInter,
                                           &content.hms.selOutput)) {
              DBG_PRINT("TMAIN: Failed to retrieve hms info\n");
            }

            if (MSP_OK != msp_rlink_GetHorn(self->rlink, &content.horn)) {
              DBG_PRINT("TMAIN: Failed to retrieve horn info\n");
            }

            if (MSP_OK != msp_rlink_GetBatteryInfo(self->rlink,
                                                   &content.battery.low,
                                                   &content.battery.gauge,
                                                   &content.battery.current)) {
              DBG_PRINT("TMAIN: Failed to retrieve battery info\n");
            }

            if (MSP_OK != msp_rlink_GetVelocity(self->rlink,
                                                &content.velocity.m1Vel,
                                                &content.velocity.m2Vel,
                                                &content.velocity.turnVel)) {
              DBG_PRINT("TMAIN: Failed to retrieve velocity info\n");
            }

            if (MSP_OK !=
                msp_rlink_GetSpeed(self->rlink,
                                   &content.speed.speed,
                                   (float*)&content.speed.trueSpeed,
                                   &content.speed.speedLimitApplied)) {
              DBG_PRINT("TMAIN: Failed to retrieve speed info\n");
            }

            for (uint8_t id = 0; id < MSP_RLINK_LIGHT_NOF; id++) {
              if (MSP_OK != msp_rlink_GetLight(self->rlink,
                                               id,
                                               &content.light[id].active,
                                               &content.light[id].lit)) {
                DBG_PRINT("TMAIN: Failed to retrieve light %d info\n", id);
              }
            }

            msp_mtx_Lock(self->incoming.cs);
            memcpy(&self->incoming.content, &content, sizeof(incoming_t));
            msp_mtx_Unlock(self->incoming.cs);
          }
        }
      } break;

      default:
        DBG_PRINT("TMAIN: Unexpected error\n");
        running = false;
        break;
    }
  }  // while

  msp_sig_MutexUnlock(self->main.signal);

  return MSP_TRD_RET_VAL;
}

static void Connect(void* rlink) {
  main_cb_t self;
  self.rlink = rlink;
  memset(&self.incoming.content, 0, sizeof(incoming_t));
  memset(&self.outgoing.content, 0, sizeof(outgoing_t));

  self.console.signal = msp_sig_Construct();
  self.console.flags = 0;
  self.wheelchair.signal = msp_sig_Construct();
  self.wheelchair.flags = 0;
  self.main.signal = msp_sig_Construct();
  self.main.flags = 0;

  // Semaphores
  self.console.started = msp_sem_Construct(0, 1);
  self.console.stopped = msp_sem_Construct(0, 1);
  self.wheelchair.started = msp_sem_Construct(0, 1);
  self.wheelchair.stopped = msp_sem_Construct(0, 1);

  msp_rlink_SetEventNotification(
      rlink,
      MSP_RLINK_EV_DISCONNECTED | MSP_RLINK_EV_ERROR | MSP_RLINK_EV_DATA_READY,
      msp_sig_GetCvar(self.main.signal),
      msp_sig_GetMutex(self.main.signal));

  // Create critical sections
  self.incoming.cs = msp_mtx_Construct();
  self.outgoing.cs = msp_mtx_Construct();

  // Create the worker threads
  self.console.thread = msp_trd_Construct((void*)ThreadConsole, (void*)&self);
  self.wheelchair.thread = msp_trd_Construct((void*)ThreadWheelchair, (void*)&self);

  // Wait until all worker threads have started
  msp_sem_Wait(self.console.started);
  msp_sem_Wait(self.wheelchair.started);

  // The main thread
  ThreadMain(&self);

  // Wait until all worker threads are closed
  msp_sem_Wait(self.console.stopped);
  msp_sem_Wait(self.wheelchair.stopped);

  msp_trd_Terminate(self.console.thread);
  msp_trd_Terminate(self.wheelchair.thread);
  msp_trd_Destruct(self.console.thread);
  msp_trd_Destruct(self.wheelchair.thread);

  msp_sem_Destruct(self.console.started);
  msp_sem_Destruct(self.console.stopped);
  msp_sem_Destruct(self.wheelchair.started);
  msp_sem_Destruct(self.wheelchair.stopped);

  // Delete critical sections
  msp_mtx_Destruct(self.incoming.cs);
  msp_mtx_Destruct(self.outgoing.cs);

  // Close the events
  msp_sig_Destruct(self.console.signal);
  msp_sig_Destruct(self.wheelchair.signal);
  msp_sig_Destruct(self.main.signal);
}

console_select_status_t console_GetIntegerOrQuit(int* value) {
  console_select_status_t status = CONSOLE_SELECT_STATUS_OK;
  char buffer[CONSOLE_BFR_SIZE];
  memset(buffer, 0, CONSOLE_BFR_SIZE);
  char* start = fgets(buffer, CONSOLE_BFR_SIZE, stdin);
  char* end = NULL;

  if (buffer[strlen(buffer) - 1] == '\n') {
    // Set the end of the string
    buffer[strlen(buffer) - 1] = '\0';

    // Try to convert it to an integer
    *value = strtol(start, &end, 10);

    // Test the input
    if (start == end) {
      // Did they type the quit?
      if (strcmp(buffer, "quit") == 0) {
        status = CONSOLE_SELECT_STATUS_QUIT;
      } else {
        status = CONSOLE_SELECT_STATUS_ERR; // This was not an integer
      }
    }
  } else {
    // To many characters were entered
    status = CONSOLE_SELECT_STATUS_ERR;
  }

  return status;
}

console_select_status_t console_Selection(console_tbl_t* table, int* selected) {
  console_select_status_t status = CONSOLE_SELECT_STATUS_OK;

  unsigned int option;

  printf("Found the following %ss:\n", table->name);
  for (size_t i = 0; i < table->nofOptions; i++) {
    printf("%3zu: %s\n", i, table->options[i]);
  }

  printf("Type the number of the %s you wish to select or 'quit' to stop.\n",
         table->name);
  printf("Select a %s: ", table->name);
  status = console_GetIntegerOrQuit((int*)&option);

  if (status == CONSOLE_SELECT_STATUS_OK) {
    if (option < table->nofOptions) {
      *selected = option;
    } else {
      status = CONSOLE_SELECT_STATUS_ERR;
      printf("Invalid choice!\n");
    }
  } else if (status == CONSOLE_SELECT_STATUS_QUIT) {
    printf("Quitting\n");
  } else {
    printf("Input not reckognized as integer!\n"); // invalid input
  }

  return status;
}

console_select_status_t console_Tables(console_tbl_t* tables,
                                       size_t nofTables,
                                       int* selected) {
  console_select_status_t status = CONSOLE_SELECT_STATUS_OK;

  for (size_t i = 0; i < nofTables; i++) {
    // Repeat until the user typed 'quit' or selected a valid option
    do {
      status = console_Selection(&tables[i], &selected[i]);
      printf("\n");
    } while (status == CONSOLE_SELECT_STATUS_ERR);

    if (status == CONSOLE_SELECT_STATUS_QUIT) {
      break;
    }
  }

  return status;
}

char** console_DevTableAlloc(msp_rlink_devices_t* devices) {
  size_t nofDevices = 0;
  msp_rlink_GetNumberOfDevices(devices, &nofDevices);
  char** tblDev =
      (char**)malloc(nofDevices * sizeof(char*));

  for (size_t i = 0; (tblDev != NULL) && (i < nofDevices); i++) {
    char* serialnumber = NULL;
    char* description = NULL;
    msp_rlink_GetDeviceSerialnumber(devices, i, &serialnumber);
    msp_rlink_GetDeviceDescription(devices, i, &description);

    size_t lenSerialnumber = strlen(serialnumber);
    size_t lenDescription = strlen(description);
    size_t length = lenSerialnumber + lenDescription + 3;

    tblDev[i] = (char*)malloc(sizeof(char) * length);

    if (tblDev[i] != NULL) {
      memcpy((void*)&tblDev[i][0], serialnumber, lenSerialnumber);
      memcpy((void*)&tblDev[i][lenSerialnumber], ": ", 2);
      memcpy((void*)&tblDev[i][lenSerialnumber + 2],
             description,
             lenDescription + 1);
    } else {
      for (i; i > 0; i--) {
        free((void*)tblDev[i]);
      }

      free(tblDev);
    }
  }

  return tblDev;
}

void console_DevTableFree(msp_rlink_devices_t* devices, char** tblDev) {
  if (tblDev != NULL) {
    size_t nofDevices = 0;
    msp_rlink_GetNumberOfDevices(devices, &nofDevices);
    for (size_t i = 0; i < nofDevices; i++) {
      if (tblDev[i] != NULL) {
        free((void*)tblDev[i]);
      }
    }

    free(tblDev);
  }
}

console_select_status_t console_GetUserInput(msp_rlink_devices_t* devices,
                                             int* selected) {
  size_t nofDevices = 0;
  msp_rlink_GetNumberOfDevices(devices, &nofDevices);
  char** tblDev = console_DevTableAlloc(devices);

  console_tbl_t tables[] = {
      {"devices", tblDev, nofDevices},
  };

  console_select_status_t status =
      console_Tables(tables, CONSOLE_SELECTION_NOF, selected);
  console_DevTableFree(devices, tblDev);

  return status;
}

int main() {
  // MEMORY_LEAK_SETUP();
  //{
  int selected[] = {0};
  msp_rlink_devices_t* devices = msp_rlink_DevicesConstruct();
  console_select_status_t status = console_GetUserInput(devices, selected);

  if (status == CONSOLE_SELECT_STATUS_OK) {
    uint8_t devid = (uint8_t)selected[CONSOLE_SELECTION_DEV];
    msp_rlink_devinfo_t *devinfo = NULL;
    msp_status_t mspstatus = msp_rlink_GetDevice(devices, devid, &devinfo);
    
    if (MSP_OK == mspstatus) {
      void* rlink = msp_rlink_Construct(devinfo);
      if (msp_rlink_SetLogFile(rlink, "somefile.log")) {
        msp_rlink_Logging(rlink, true);
        mspstatus = msp_rlink_Open(rlink);

        if (mspstatus == MSP_OK) {
          Connect(rlink);
          mspstatus = msp_rlink_Close(rlink);
        } else {
          printf("Failed to open rlink (%u)\n", mspstatus);
        }
      } else {
        printf("Failed to create the log file\n");
      }

      msp_rlink_Destruct(rlink);
    } else {
      printf("Failed to get device info\n");
    }
  }

  msp_rlink_DevicesDestruct(devices);
  printf("Done\n");
  //}
  // MEMORY_LEAK_TEARDOWN();
  return 0;
}
