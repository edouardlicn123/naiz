#ifndef SCENEVM_H
#define SCENEVM_H

#define SCENE_STATUS_RENDERTEXT    0x0001
#define SCENE_STATUS_WIPETEXT      0x0002
#define SCENE_STATUS_MAKING_CHOICE 0x0004
#define SCENE_STATUS_FINALEND      0x4000
#define SCENE_STATUS_ERROR         0x8000

#define SELECT_UP   (-1)
#define SELECT_DOWN   1

typedef struct
{
    unsigned short num_scenes;
    unsigned short num_chars;
    unsigned short cur_scene;
} SceneInfo;

extern SceneInfo scene_info;
extern int return_status;
extern unsigned char cur_async_actions;

int setup_scene_engine(void);
int free_scene_engine(void);
void control_process(unsigned char process);
void switch_choice(char dir);
void commit_choice(void);
void end_user_wait(void);
void scene_async_action_process(void);
int scene_data_process(void);

#endif
