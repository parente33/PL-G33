C =========================================================
C TESTE 4 - ARITHMETIC IF
C =========================================================
      PROGRAM ARIF
      INTEGER X
      X = -2
      IF (X) 10,20,30
  10  PRINT *, 'NEGATIVO'
      GOTO 40
  20  PRINT *, 'ZERO'
      GOTO 40
  30  PRINT *, 'POSITIVO'
  40  CONTINUE
      END