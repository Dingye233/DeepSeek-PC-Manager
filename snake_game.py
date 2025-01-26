import pygame
import random
import time

# 初始化pygame
pygame.init()

# 颜色定义
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)

# 游戏窗口大小
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

# 蛇的方块大小和移动速度
BLOCK_SIZE = 20
SPEED = 15

# 创建游戏窗口
window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption('贪吃蛇')

# 时钟控制
clock = pygame.time.Clock()

# 字体设置
font = pygame.font.SysFont(None, 50)

def draw_snake(snake_list):
    for x, y in snake_list:
        pygame.draw.rect(window, GREEN, [x, y, BLOCK_SIZE, BLOCK_SIZE])

def message(msg, color):
    text = font.render(msg, True, color)
    window.blit(text, [WINDOW_WIDTH/6, WINDOW_HEIGHT/3])

def game_loop():
    game_over = False
    game_close = False

    # 初始位置和移动方向
    x = WINDOW_WIDTH / 2
    y = WINDOW_HEIGHT / 2
    x_change = 0
    y_change = 0

    snake_list = []
    snake_length = 1

    # 生成食物位置
    food_x = round(random.randrange(0, WINDOW_WIDTH - BLOCK_SIZE) / BLOCK_SIZE) * BLOCK_SIZE
    food_y = round(random.randrange(0, WINDOW_HEIGHT - BLOCK_SIZE) / BLOCK_SIZE) * BLOCK_SIZE

    while not game_over:
        while game_close:
            window.fill(BLACK)
            message("游戏结束！按Q退出或C重新开始", RED)
            pygame.display.update()

            # 处理游戏结束后的输入
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        game_over = True
                        game_close = False
                    if event.key == pygame.K_c:
                        game_loop()

        # 处理键盘事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game_over = True
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT and x_change == 0:
                    x_change = -BLOCK_SIZE
                    y_change = 0
                elif event.key == pygame.K_RIGHT and x_change == 0:
                    x_change = BLOCK_SIZE
                    y_change = 0
                elif event.key == pygame.K_UP and y_change == 0:
                    y_change = -BLOCK_SIZE
                    x_change = 0
                elif event.key == pygame.K_DOWN and y_change == 0:
                    y_change = BLOCK_SIZE
                    x_change = 0

        # 边界检测
        if x >= WINDOW_WIDTH or x < 0 or y >= WINDOW_HEIGHT or y < 0:
            game_close = True

        # 更新位置
        x += x_change
        y += y_change
        
        window.fill(BLACK)
        pygame.draw.rect(window, RED, [food_x, food_y, BLOCK_SIZE, BLOCK_SIZE])
        
        snake_head = []
        snake_head.append(x)
        snake_head.append(y)
        snake_list.append(snake_head)
        
        if len(snake_list) > snake_length:
            del snake_list[0]

        # 检测是否吃到自己
        for segment in snake_list[:-1]:
            if segment == snake_head:
                game_close = True

        draw_snake(snake_list)
        pygame.display.update()

        # 吃到食物
        if x == food_x and y == food_y:
            food_x = round(random.randrange(0, WINDOW_WIDTH - BLOCK_SIZE) / BLOCK_SIZE) * BLOCK_SIZE
            food_y = round(random.randrange(0, WINDOW_HEIGHT - BLOCK_SIZE) / BLOCK_SIZE) * BLOCK_SIZE
            snake_length += 1

        clock.tick(SPEED)

    pygame.quit()
    quit()

# 启动游戏
game_loop()