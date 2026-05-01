C =========================================================
C TESTE 7 - ARRAY 2D
C =========================================================
      PROGRAM MAT2D
      INTEGER M(2,3)
      INTEGER I, J
      DO 20 I = 1, 2
          DO 10 J = 1, 3
              M(I,J) = I + J
  10      CONTINUE
  20  CONTINUE
      PRINT *, M(2,3)
      END