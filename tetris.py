import pygame
import random

# 初始化pygame
pygame.init()

# 定义颜色
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
COLORS = [
    (0, 255, 255),
    (255, 255, 0),
    (255, 165, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 0, 255),
    (255, 0, 0)
]

# 定义方块形状
SHAPES = [
    [[1, 1, 1, 1]],
    [[1, 1], [1, 1]],
    [[1, 1, 0], [0, 1, 1]],
    [[0, 1, 1], [1, 1, 0]],
    [[1, 1, 1], [0, 1, 0]],
    [[1, 1, 1], [1, 0, 0]],
    [[1, 1, 1], [0, 0, 1]]
]

# 定义游戏区域大小
WIDTH = 300
HEIGHT = 600
BLOCK_SIZE = 30

# 创建游戏窗口
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('俄罗斯方块')

# 定义时钟
clock = pygame.time.Clock()

# 定义方块类
class Block:
    def __init__(self, shape):
        self.shape = shape
        self.color = random.choice(COLORS)
        self.x = (WIDTH // BLOCK_SIZE // 2) - (len(shape[0]) // 2)
        self.y = 0

    def draw(self):
        for i in range(len(self.shape)):
            for j in range(len(self.shape[i])):
                if self.shape[i][j]:
                    pygame.draw.rect(screen, self.color, (self.x * BLOCK_SIZE + j * BLOCK_SIZE, self.y * BLOCK_SIZE + i * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE))

    def move_down(self):
        self.y += 1

    def move_left(self):
        self.x -= 1

    def move_right(self):
        self.x += 1

    def rotate(self):
        self.shape = [list(row) for row in zip(*self.shape[::-1])]

# 定义游戏区域
board = [[0 for _ in range(WIDTH // BLOCK_SIZE)] for _ in range(HEIGHT // BLOCK_SIZE)]

# 定义函数来检查方块是否碰到边界或其他方块
def check_collision(block, board):
    for i in range(len(block.shape)):
        for j in range(len(block.shape[i])):
            if block.shape[i][j]:
                if block.y + i >= len(board) or block.x + j < 0 or block.x + j >= len(board[0]) or board[block.y + i][block.x + j]:
                    return True
    return False

# 定义函数来将方块固定到游戏区域
def fix_block(block, board):
    for i in range(len(block.shape)):
        for j in range(len(block.shape[i])):
            if block.shape[i][j]:
                board[block.y + i][block.x + j] = block.color

# 定义函数来消除满行
def clear_lines(board):
    lines_to_clear = [i for i, row in enumerate(board) if all(row)]
    for i in lines_to_clear:
        del board[i]
        board.insert(0, [0 for _ in range(len(board[0]))])
    return len(lines_to_clear)

# 定义函数来绘制游戏区域
def draw_board(board):
    for i in range(len(board)):
        for j in range(len(board[i])):
            if board[i][j]:
                pygame.draw.rect(screen, board[i][j], (j * BLOCK_SIZE, i * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE))
            else:
                pygame.draw.rect(screen, GRAY, (j * BLOCK_SIZE, i * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE), 1)

# 主循环
def main():
    global board
    block = Block(random.choice(SHAPES))
    game_over = False
    score = 0

    while not game_over:
        screen.fill(BLACK)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game_over = True
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    block.move_left()
                    if check_collision(block, board):
                        block.move_right()
                if event.key == pygame.K_RIGHT:
                    block.move_right()
                    if check_collision(block, board):
                        block.move_left()
                if event.key == pygame.K_DOWN:
                    block.move_down()
                    if check_collision(block, board):
                        block.y -= 1
                if event.key == pygame.K_UP:
                    block.rotate()
                    if check_collision(block, board):
                        for _ in range(3):
                            block.rotate()

        block.move_down()
        if check_collision(block, board):
            block.y -= 1
            fix_block(block, board)
            score += clear_lines(board)
            block = Block(random.choice(SHAPES))
            if check_collision(block, board):
                game_over = True

        draw_board(board)
        block.draw()
        pygame.display.flip()
        clock.tick(5)

    pygame.quit()

if __name__ == '__main__':
    main()