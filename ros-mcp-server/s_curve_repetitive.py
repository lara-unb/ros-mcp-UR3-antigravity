import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import time

# URScript with a while loop for infinite repetition
urscript = """def repetitive_s_curve():
  p_start = get_actual_tcp_pose()
  
  while (True):
    # Forward S-curve
    movel(pose_trans(p_start, p[0.0, 0.03, 0.02, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.0, 0.04, 0.04, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.0, 0.03, 0.06, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.0, 0.00, 0.08, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.0, -0.03, 0.10, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.0, -0.04, 0.12, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.0, -0.03, 0.14, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    movel(pose_trans(p_start, p[0.0, 0.00, 0.16, 0, 0, 0]), a=0.2, v=0.1, r=0.01)
    
    # Return to start smoothly
    movel(p_start, a=0.2, v=0.1, r=0.0)
    
    sync() # Ensure synchronization with the controller
  end
end
"""

def main():
    rclpy.init()
    node = rclpy.create_node('s_curve_repeater')
    pub = node.create_publisher(String, '/urscript_interface/script_command', 10)
    msg = String()
    msg.data = urscript
    
    # Wait for subscribers to connect
    time.sleep(1.0)
    
    pub.publish(msg)
    node.get_logger().info("Published infinite Repetitive S-curve URScript")
    
    time.sleep(1.0)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
