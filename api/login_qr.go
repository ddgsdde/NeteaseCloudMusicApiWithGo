package api

import (
	"github.com/gin-gonic/gin"
	"singo/service"
)

func LoginQrKey(c *gin.Context) {
	var s service.LoginQrKeyService
	if err := c.ShouldBind(&s); err == nil {
		res := s.LoginQrKey(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}

func LoginQrCreate(c *gin.Context) {
	var s service.LoginQrCreateService
	if err := c.ShouldBind(&s); err == nil {
		res := s.LoginQrCreate(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}

func LoginQrCheck(c *gin.Context) {
	var s service.LoginQrCheckService
	if err := c.ShouldBind(&s); err == nil {
		res := s.LoginQrCheck(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}
